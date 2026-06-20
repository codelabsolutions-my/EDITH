"""The LLM provider seam + the deterministic ``StubLLM`` used in M0.

``LLMProvider`` is the single interface the agent loop streams from. M2 plugs in
``IlmuLLM`` / ``FrontierLLM`` behind it; M0 ships :class:`StubLLM`, which needs no
API key and emits canned text plus **deterministic** tool calls on trigger
phrases — enough to exercise the whole agent surface (tools, confirm, barge-in).
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

# A chat message: ``{"role": ..., "content": ...}`` plus optional tool metadata.
Message = dict[str, Any]


@dataclass(frozen=True)
class ToolSpec:
    """An LLM-facing tool description (built from a connector :class:`Tool`)."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema (object)


@dataclass(frozen=True)
class ToolCall:
    """A model's request to invoke a tool."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class TextDelta:
    """A streamed chunk of assistant text."""

    text: str


@dataclass(frozen=True)
class ToolCallDelta:
    """A streamed tool-call request."""

    call: ToolCall


@dataclass(frozen=True)
class TurnEnd:
    """The model finished this streaming pass."""

    finish_reason: str


LLMDelta = TextDelta | ToolCallDelta | TurnEnd


class LLMProvider(abc.ABC):
    """Streaming LLM interface — the loop's only view of the model."""

    @abc.abstractmethod
    def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        *,
        cancel: Any,
    ) -> AsyncIterator[LLMDelta]:
        """Stream deltas for the given messages. ``cancel`` is an asyncio.Event."""
        raise NotImplementedError


# ─── M0: deterministic stub ───────────────────────────────────────────────

# Trigger phrase -> tool name. Checked in order; first match wins.
_TRIGGERS: tuple[tuple[str, str], ...] = (
    ("self destruct", "self_destruct"),
    ("remember", "remember"),
    ("what time", "current_time"),
    ("current time", "current_time"),
    ("echo ", "echo"),
)


@dataclass
class StubLLM(LLMProvider):
    """A deterministic, network-free LLM for the M0 text demo.

    On a user message it scans for a trigger phrase and, if found, emits a single
    :class:`ToolCallDelta`. When the latest message is a tool result fed back by
    the loop, it emits a short acknowledgement and ends the turn. With no trigger
    it returns a canned greeting.
    """

    _counter: int = field(default=0, init=False)

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        *,
        cancel: Any,
    ) -> AsyncIterator[LLMDelta]:
        last = messages[-1] if messages else {}
        role = last.get("role")

        if role == "tool":
            # The loop fed a tool result back — acknowledge and finish.
            name = last.get("name", "the tool")
            yield TextDelta(text=f"Done — {name} sorted. ")
            yield TurnEnd(finish_reason="stop")
            return

        user_text = str(last.get("content", "")) if role == "user" else ""
        lowered = user_text.lower()

        tool_name = self._match_trigger(lowered, tools)
        if tool_name is not None:
            self._counter += 1
            yield ToolCallDelta(
                call=ToolCall(
                    id=f"call_{self._counter}",
                    name=tool_name,
                    arguments=self._arguments_for(tool_name, user_text),
                )
            )
            yield TurnEnd(finish_reason="tool_calls")
            return

        # No trigger — a plain conversational reply.
        yield TextDelta(text="Hey, I'm EDITH. ")
        yield TextDelta(text="Tell me to remember something or ask the time lah. ")
        yield TurnEnd(finish_reason="stop")

    @staticmethod
    def _match_trigger(lowered: str, tools: Sequence[ToolSpec]) -> str | None:
        available = {t.name for t in tools}
        for phrase, name in _TRIGGERS:
            if phrase in lowered and name in available:
                return name
        return None

    @staticmethod
    def _arguments_for(tool_name: str, user_text: str) -> dict[str, Any]:
        if tool_name == "remember":
            return {"text": _after(user_text, "remember")}
        if tool_name == "echo":
            return {"text": _after(user_text, "echo ")}
        return {}


def _after(text: str, marker: str) -> str:
    """Return the text following the first case-insensitive ``marker``, trimmed."""
    idx = text.lower().find(marker.lower())
    if idx == -1:
        return text.strip()
    return text[idx + len(marker) :].strip()
