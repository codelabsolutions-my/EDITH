"""Per-connection session lifecycle.

A :class:`Session` wires the M0 runtime together — a :class:`TextTransport`, a
:class:`ToolCatalog` over the shared connector registry, an in-memory
:class:`Memory`, a :class:`ConfirmGate`, a :class:`StubLLM` and the
:class:`AgentLoop` — and runs two cooperating tasks: one demuxes WebSocket frames
into the inbound event queue, the other runs the agent loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .agent.catalog import ToolCatalog
from .agent.confirm import ConfirmGate
from .agent.llm import StubLLM
from .agent.loop import AgentLoop
from .agent.memory import Memory
from .connectors.registry import ConnectorRegistry
from .events import (
    AudioFrameIn,
    BargeInHint,
    ConfirmReply,
    InboundEvent,
    TextIn,
)
from .voice.text_transport import _CLOSE, TextTransport, WsSend

log = logging.getLogger("edith.session")

# Receives the next inbound WS message as either a dict (JSON) or bytes (binary),
# or raises on disconnect.
WsReceive = Callable[[], Awaitable["WsMessage"]]


class WsMessage:
    """A received WebSocket frame: exactly one of ``json`` or ``bytes`` is set."""

    __slots__ = ("bytes", "json")

    def __init__(self, *, json: dict[str, Any] | None = None, bytes: bytes | None = None) -> None:
        self.json = json
        self.bytes = bytes


class Session:
    """One authenticated WebSocket connection's runtime."""

    def __init__(
        self,
        *,
        user_id: str,
        registry: ConnectorRegistry,
        ws_send: WsSend,
        ws_receive: WsReceive,
    ) -> None:
        self._user_id = user_id
        self._ws_receive = ws_receive
        self._inbound: asyncio.Queue[InboundEvent | object] = asyncio.Queue()
        self._memory = Memory()
        self._transport = TextTransport(self._inbound, ws_send)
        catalog = ToolCatalog(
            registry,
            user_id=user_id,
            cred_lookup=lambda _key: None,  # M0: identity-only, no connector creds
            extra={"memory": self._memory},
        )
        self._loop = AgentLoop(
            user_id=user_id,
            transport=self._transport,
            llm=StubLLM(),
            catalog=catalog,
            memory=self._memory,
            confirm_gate=ConfirmGate(),
        )

    async def run(self) -> None:
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._demux())
                tg.create_task(self._transport.pump())
                tg.create_task(self._loop.run())
        finally:
            await self._transport.close()

    async def _demux(self) -> None:
        """Translate raw WS frames into typed inbound events."""
        try:
            while True:
                msg = await self._ws_receive()
                if msg.bytes is not None:
                    # M0 is text-only; keep the path for voice but ignore audio.
                    await self._inbound.put(AudioFrameIn(data=msg.bytes))
                    continue
                payload = msg.json or {}
                event = self._decode(payload)
                if event is not None:
                    await self._inbound.put(event)
        except (StopAsyncIteration, asyncio.CancelledError):
            pass
        except Exception:
            log.info("ws receive ended", extra={"user_id": self._user_id})
        finally:
            # Unblock user_turns so the agent task can finish.
            await self._inbound.put(_CLOSE)

    def _decode(self, payload: dict[str, Any]) -> InboundEvent | None:
        # Barge-in detection for a mid-turn TextIn lives in the transport's
        # user_turns (it owns turn-active state); the session only types events.
        match payload.get("type"):
            case "text":
                return TextIn(text=str(payload.get("content", "")))
            case "confirm":
                return ConfirmReply(
                    action_id=str(payload.get("action_id", "")),
                    ok=bool(payload.get("ok", False)),
                )
            case "barge_in":
                return BargeInHint()
            case _:
                log.info(
                    "ignoring unknown inbound type",
                    extra={"user_id": self._user_id, "msg_type": payload.get("type")},
                )
                return None
