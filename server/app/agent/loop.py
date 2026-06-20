"""The agent loop — the streaming tool-call orchestrator.

The heart of the system, and the one place tools, confirmation, barge-in and
memory are coordinated. It drives a :class:`~app.voice.transport.Transport` it
knows nothing concrete about, so the same loop serves text (M0) and voice (M2).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ..connectors.base import ToolClass
from ..events import (
    ErrorEvent,
    LLMToken,
    Status,
    ToolEvent,
    Transcript,
    TurnComplete,
)
from ..voice.transport import Transport
from .catalog import ToolCatalog
from .confirm import ConfirmGate, TurnCancelled
from .llm import (
    LLMProvider,
    Message,
    TextDelta,
    ToolCall,
    ToolCallDelta,
    TurnEnd,
)
from .memory import Memory
from .prompts import system_prompt

log = logging.getLogger("edith.agent")

# Cap tool-call rounds per turn so a misbehaving model can't loop forever.
_MAX_TOOL_ROUNDS = 8


@dataclass
class ActionLogEntry:
    """One executed action. Kept in-memory for the turn and (when wired) persisted."""

    user_id: str
    tool: str
    args_summary: str
    result_summary: str


@runtime_checkable
class TurnRecorder(Protocol):
    """Optional persistence seam: where messages and actions are durably written.

    The loop stays oblivious to storage — a ``None`` recorder (tests, DB-less runs)
    means nothing is persisted; a Postgres-backed recorder writes ``messages`` and
    ``action_log`` rows. All methods are awaited off the agent's critical decisions.
    """

    async def record_message(self, role: str, content: str) -> None: ...

    async def record_action(self, entry: ActionLogEntry) -> None: ...


class AgentLoop:
    """Runs user turns: recall -> stream LLM -> dispatch tools -> reply."""

    def __init__(
        self,
        *,
        user_id: str,
        transport: Transport,
        llm: LLMProvider,
        catalog: ToolCatalog,
        memory: Memory,
        confirm_gate: ConfirmGate,
        recorder: TurnRecorder | None = None,
    ) -> None:
        self._user_id = user_id
        self._transport = transport
        self._llm = llm
        self._catalog = catalog
        self._memory = memory
        self._confirm = confirm_gate
        self._recorder = recorder
        # Per-process audit trail for the turn; durable copy goes through the recorder.
        self.action_log: list[ActionLogEntry] = []
        # Detached post-turn tasks (memory extraction); kept to avoid GC.
        self._background: set[asyncio.Task[None]] = set()

    async def run(self) -> None:
        async for turn in self._transport.user_turns():
            cancel = asyncio.Event()
            watcher = asyncio.create_task(self._watch_barge_in(turn_cancel=cancel))
            try:
                await self._run_turn(turn.text, cancel)
            except TurnCancelled:
                log.info("turn cancelled (barge-in)", extra={"user_id": self._user_id})
                await self._transport.set_status(Status.LISTENING)
            except Exception:
                log.exception("turn failed", extra={"user_id": self._user_id})
                await self._transport.emit(
                    ErrorEvent(code="agent_error", message="Sorry, something went wrong.")
                )
                await self._transport.set_status(Status.IDLE)
            finally:
                watcher.cancel()

    async def _watch_barge_in(self, *, turn_cancel: asyncio.Event) -> None:
        """Link the transport's barge-in signal to this turn's cancel event."""
        try:
            await self._transport.barge_in_signal().wait()
            turn_cancel.set()
        except asyncio.CancelledError:
            pass

    def _cancelled(self, cancel: asyncio.Event) -> bool:
        # The barge-in signal is the source of truth; the per-turn ``cancel`` event
        # mirrors it for propagation into ``stream()``. Checking the signal here
        # makes cancellation independent of the watcher task being scheduled.
        return cancel.is_set() or self._transport.barge_in_signal().is_set()

    async def _run_turn(self, user_text: str, cancel: asyncio.Event) -> None:
        if self._cancelled(cancel):
            raise TurnCancelled
        await self._transport.set_status(Status.THINKING)
        await self._transport.emit(Transcript(role="user", text=user_text, final=True))
        await self._record_message("user", user_text)

        memories = await self._memory.recall(self._user_id, user_text)
        messages: list[Message] = [
            {"role": "system", "content": system_prompt(memories)},
            {"role": "user", "content": user_text},
        ]
        specs = self._catalog.specs()

        reply_parts: list[str] = []
        for _ in range(_MAX_TOOL_ROUNDS):
            calls: list[ToolCall] = []
            round_text: list[str] = []
            async for delta in self._llm.stream(messages, specs, cancel=cancel):
                if self._cancelled(cancel):
                    raise TurnCancelled
                if isinstance(delta, TextDelta):
                    reply_parts.append(delta.text)
                    round_text.append(delta.text)
                    await self._transport.emit(LLMToken(text=delta.text))
                elif isinstance(delta, ToolCallDelta):
                    calls.append(delta.call)
                elif isinstance(delta, TurnEnd):
                    break

            if not calls:
                break

            # Append the assistant's tool-call message before the tool results so the
            # transcript fed back to the model is OpenAI-compatible (a tool result must
            # follow the assistant turn that requested it).
            messages.append(
                {
                    "role": "assistant",
                    "content": "".join(round_text) or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in calls
                    ],
                }
            )
            for call in calls:
                result = await self._dispatch(call, cancel)
                messages.append(
                    {
                        "role": "tool",
                        "name": call.name,
                        "tool_call_id": call.id,
                        "content": json.dumps(result),
                    }
                )
        else:
            log.warning("max tool rounds reached", extra={"user_id": self._user_id})

        reply = "".join(reply_parts)
        if reply.strip():
            await self._record_message("edith", reply)
        await self._transport.flush_output()
        await self._transport.emit(TurnComplete())
        await self._transport.set_status(Status.IDLE)
        self._schedule_extract(user_text, reply)

    async def _dispatch(self, call: ToolCall, cancel: asyncio.Event) -> dict[str, Any]:
        tool = self._catalog.lookup(call.name)
        if tool is None:
            await self._transport.emit(ToolEvent(name=call.name, state="error"))
            return {"error": f"unknown tool: {call.name}"}

        await self._transport.emit(ToolEvent(name=call.name, state="running"))

        if tool.tool_class is ToolClass.CONFIRM:
            summary = self._confirm_summary(call)
            ok = await self._confirm.await_reply(call.id, summary, self._transport, cancel)
            if not ok:
                await self._transport.emit(ToolEvent(name=call.name, state="done"))
                return {"skipped": True, "reason": "user declined"}

        try:
            result = await tool.handler(**call.arguments)
        except Exception as exc:
            log.exception("tool failed", extra={"user_id": self._user_id, "tool": call.name})
            await self._transport.emit(ToolEvent(name=call.name, state="error"))
            return {"error": str(exc)}

        entry = ActionLogEntry(
            user_id=self._user_id,
            tool=call.name,
            args_summary=_summarise(call.arguments),
            result_summary=_summarise(result),
        )
        self.action_log.append(entry)
        await self._record_action(entry)
        await self._transport.emit(ToolEvent(name=call.name, state="done"))
        return result if isinstance(result, dict) else {"result": result}

    @staticmethod
    def _confirm_summary(call: ToolCall) -> str:
        if call.arguments:
            return f"Run {call.name} with {_summarise(call.arguments)} — ok?"
        return f"Run {call.name} — ok?"

    async def _record_message(self, role: str, content: str) -> None:
        if self._recorder is None:
            return
        try:
            await self._recorder.record_message(role, content)
        except Exception:
            # Persistence must never break a live turn; log and carry on.
            log.exception("record_message failed", extra={"user_id": self._user_id})

    async def _record_action(self, entry: ActionLogEntry) -> None:
        if self._recorder is None:
            return
        try:
            await self._recorder.record_action(entry)
        except Exception:
            log.exception("record_action failed", extra={"user_id": self._user_id})

    def _schedule_extract(self, user_text: str, reply_text: str) -> None:
        task = asyncio.create_task(
            self._memory.extract_after_turn(self._user_id, user_text, reply_text)
        )
        self._background.add(task)
        task.add_done_callback(self._background.discard)


def _summarise(value: Any, *, limit: int = 120) -> str:
    """Short, content-light summary for the action log (no PII dumps)."""
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"
