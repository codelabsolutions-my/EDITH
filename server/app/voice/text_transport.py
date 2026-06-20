"""Text-mode transport (M0) — text in -> agent -> text out, no ILMU, no audio.

``TextTransport`` consumes an inbound event queue fed by the WebSocket demux in
:mod:`app.session`, and serialises outbound events to JSON via an injected
``ws_send`` callable. It implements the same :class:`~app.voice.transport.Transport`
contract the voice pipeline will, so the agent loop is mode-agnostic.

A dedicated ``pump`` coroutine drains the raw inbound queue *continuously* and
routes events: it resolves pending confirmations, sets the barge-in signal, and
feeds turn text into an internal turns queue that :meth:`user_turns` consumes.
This decoupling matters — while the agent loop is blocked inside
:meth:`request_confirm` awaiting a reply, it is **not** iterating ``user_turns``,
so the confirm reply must be drained by an independent task or it would never
resolve.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from ..events import (
    AudioFrameIn,
    BargeInHint,
    ConfirmReply,
    ConfirmRequest,
    ErrorEvent,
    InboundEvent,
    LLMToken,
    OutboundEvent,
    Status,
    StatusEvent,
    TextIn,
    ToolEvent,
    Transcript,
    TurnComplete,
)
from .transport import Transport, UserTurn

# A JSON-shaped message sender (e.g. ``websocket.send_json``).
WsSend = Callable[[dict[str, Any]], Awaitable[None]]

# Sentinel pushed onto a queue to end consumption cleanly on disconnect.
_CLOSE = object()


class TextTransport(Transport):
    """Transport over a JSON WebSocket for the text-mode agent."""

    def __init__(self, inbound: asyncio.Queue[InboundEvent | object], ws_send: WsSend) -> None:
        self._inbound = inbound
        self._ws_send = ws_send
        self._barge_in = asyncio.Event()
        # Turns demuxed by the pump, consumed by user_turns.
        self._turns: asyncio.Queue[UserTurn | object] = asyncio.Queue()
        # Pending confirmations, keyed by action_id, awaited by request_confirm.
        self._pending: dict[str, asyncio.Future[bool]] = {}
        # True while the agent is mid-turn — a TextIn arriving now is a barge-in.
        self._turn_active = False

    @property
    def turn_active(self) -> bool:
        return self._turn_active

    async def pump(self) -> None:
        """Continuously drain the raw inbound queue and route events.

        Runs for the life of the session, independent of the agent loop, so
        confirm replies and barge-in are handled even while a turn is blocked.
        """
        while True:
            item = await self._inbound.get()
            if item is _CLOSE:
                await self._turns.put(_CLOSE)
                return
            event = item  # narrowed below
            if isinstance(event, TextIn):
                if self._turn_active:
                    # Interrupting a turn already in flight — barge-in. Hand the
                    # text on as the next turn; the current turn unwinds first.
                    self._barge_in.set()
                await self._turns.put(UserTurn(text=event.text, audio_present=False))
            elif isinstance(event, ConfirmReply):
                fut = self._pending.pop(event.action_id, None)
                if fut is not None and not fut.done():
                    fut.set_result(event.ok)
            elif isinstance(event, BargeInHint):
                self._barge_in.set()
            elif isinstance(event, AudioFrameIn):
                continue  # M0: text-only, ignore audio frames

    async def user_turns(self) -> AsyncIterator[UserTurn]:
        while True:
            item = await self._turns.get()
            if item is _CLOSE or not isinstance(item, UserTurn):
                return
            # A fresh turn starts — clear any stale barge-in from the prior turn.
            self._barge_in = asyncio.Event()
            self._turn_active = True
            yield item

    async def emit(self, event: OutboundEvent) -> None:
        if isinstance(event, TurnComplete):
            # The turn finished; subsequent text starts a new turn, not a barge-in.
            self._turn_active = False
        await self._ws_send(self._serialise(event))

    async def set_status(self, status: Status) -> None:
        # On barge-in the loop transitions to LISTENING (no TurnComplete is sent),
        # so this is where a cancelled turn becomes inactive.
        if status in (Status.LISTENING, Status.IDLE):
            self._turn_active = False
        await self.emit(StatusEvent(state=status))

    async def request_confirm(self, action_id: str, summary: str) -> bool:
        fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._pending[action_id] = fut
        await self.emit(ConfirmRequest(action_id=action_id, summary=summary))
        try:
            return await fut
        finally:
            self._pending.pop(action_id, None)

    def barge_in_signal(self) -> asyncio.Event:
        return self._barge_in

    async def flush_output(self) -> None:
        # Text mode writes synchronously per emit; nothing to drain.
        return None

    async def close(self) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

    @staticmethod
    def _serialise(event: OutboundEvent) -> dict[str, Any]:
        match event:
            case StatusEvent(state=state):
                return {"type": "status", "state": state.value}
            case LLMToken(text=text):
                return {"type": "transcript", "role": "edith", "text": text, "final": False}
            case Transcript(role=role, text=text, final=final):
                return {"type": "transcript", "role": role, "text": text, "final": final}
            case ConfirmRequest(action_id=action_id, summary=summary):
                return {"type": "confirm_request", "action_id": action_id, "summary": summary}
            case ToolEvent(name=name, state=state):
                return {"type": "tool_event", "name": name, "state": state}
            case ErrorEvent(code=code, message=message):
                return {"type": "error", "code": code, "message": message}
            case TurnComplete():
                return {"type": "turn_end"}
            case _:
                # AudioFrameOut and any future binary events are not JSON-serialised
                # in text mode; the voice transport handles them as binary frames.
                raise TypeError(f"text transport cannot serialise {type(event).__name__}")
