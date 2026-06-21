"""Per-connection session lifecycle.

A :class:`Session` wires the runtime together — a :class:`TextTransport`, a
:class:`ToolCatalog` over the shared connector registry, a :class:`Memory`, a
:class:`ConfirmGate`, an :class:`LLMProvider` and the :class:`AgentLoop` — and runs
the demux + agent-loop tasks.

Persistence is optional: with a database pool the session uses the Postgres-backed
:class:`PgMemory`, records the conversation + messages, and writes ``action_log``;
without one (tests, DB-less demo) it falls back to in-memory storage. The agent
loop is identical either way — storage is hidden behind the ``Memory`` and
:class:`~app.agent.loop.TurnRecorder` seams.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import asyncpg

from . import repositories as repo
from .agent.catalog import ToolCatalog
from .agent.confirm import ConfirmGate
from .agent.llm import LLMProvider, StubLLM
from .agent.llm_ilmu import IlmuLLM
from .agent.loop import ActionLogEntry, AgentLoop
from .agent.memory import InMemoryMemory, Memory, PgMemory
from .config import Settings, get_settings
from .connectors.registry import ConnectorRegistry
from .events import (
    AudioFrameIn,
    BargeInHint,
    ConfirmReply,
    InboundEvent,
    TextIn,
)
from .integrations.credentials import build_credentials
from .proactivity.reminders import ReminderStore
from .voice.asr import IlmuASR
from .voice.pipeline import VoicePipeline, WsSendBytes
from .voice.text_transport import _CLOSE, TextTransport, WsSend
from .voice.transport import Transport
from .voice.tts import IlmuTTS

log = logging.getLogger("edith.session")

WsReceive = Callable[[], Awaitable["WsMessage"]]


class WsMessage:
    """A received WebSocket frame: exactly one of ``json`` or ``bytes`` is set."""

    __slots__ = ("bytes", "json")

    def __init__(self, *, json: dict[str, Any] | None = None, bytes: bytes | None = None) -> None:
        self.json = json
        self.bytes = bytes


class PgTurnRecorder:
    """Persists messages + actions for one conversation to Postgres."""

    def __init__(self, pool: asyncpg.Pool, *, user_id: str, conversation_id: UUID) -> None:
        self._pool = pool
        self._user_id = user_id
        self._conversation_id = conversation_id

    async def record_message(self, role: str, content: str) -> None:
        async with self._pool.acquire() as conn:
            await repo.insert_message(
                conn,
                conversation_id=self._conversation_id,
                user_id=self._user_id,
                role=role,
                content=content,
            )

    async def record_action(self, entry: ActionLogEntry) -> None:
        async with self._pool.acquire() as conn:
            await repo.insert_action(
                conn,
                user_id=entry.user_id,
                tool=entry.tool,
                args_summary=entry.args_summary,
                result_summary=entry.result_summary,
            )


class Session:
    """One authenticated WebSocket connection's runtime."""

    def __init__(
        self,
        *,
        user_id: str,
        registry: ConnectorRegistry,
        ws_send: WsSend,
        ws_receive: WsReceive,
        db_pool: asyncpg.Pool | None = None,
        settings: Settings | None = None,
        llm: LLMProvider | None = None,
        ws_send_bytes: WsSendBytes | None = None,
        mode: str = "text",
    ) -> None:
        self._user_id = user_id
        self._registry = registry
        self._ws_receive = ws_receive
        self._db_pool = db_pool
        self._settings = settings or get_settings()
        self._llm_override = llm
        self._inbound: asyncio.Queue[InboundEvent | object] = asyncio.Queue()
        self._conversation_id: UUID | None = None
        self._transport = self._build_transport(mode, ws_send, ws_send_bytes)

    def _build_transport(
        self, mode: str, ws_send: WsSend, ws_send_bytes: WsSendBytes | None
    ) -> Transport:
        """Voice mode needs ILMU + a binary sender; otherwise fall back to text."""
        if mode == "voice" and self._settings.voice_enabled and ws_send_bytes is not None:
            log.info("voice mode", extra={"user_id": self._user_id})
            return VoicePipeline(
                self._inbound,
                ws_send,
                ws_send_bytes,
                IlmuASR(self._settings),
                IlmuTTS(self._settings),
                settings=self._settings,
                usage_sink=self._record_usage,
            )
        if mode == "voice":
            log.warning(
                "voice requested but unavailable (no ILMU key / binary channel) — using text",
                extra={"user_id": self._user_id},
            )
        return TextTransport(self._inbound, ws_send)

    async def _record_usage(self, kind: str, seconds: float) -> None:
        if self._db_pool is None:
            return
        async with self._db_pool.acquire() as conn:
            await repo.insert_usage(
                conn, user_id=self._user_id, call_type=kind, voice_seconds=seconds
            )

    def _build_llm(self) -> LLMProvider:
        if self._llm_override is not None:
            return self._llm_override
        if self._settings.ILMU_API_KEY and self._settings.ILMU_API_BASE:
            log.info("using ILMU LLM", extra={"model": self._settings.ILMU_TOOL_MODEL})
            return IlmuLLM(self._settings)
        log.info("using StubLLM (no ILMU key configured)")
        return StubLLM()

    async def _build_persistence(self) -> tuple[Memory, PgTurnRecorder | None]:
        if self._db_pool is None:
            return InMemoryMemory(), None
        async with self._db_pool.acquire() as conn:
            self._conversation_id = await repo.create_conversation(conn, user_id=self._user_id)
        recorder = PgTurnRecorder(
            self._db_pool, user_id=self._user_id, conversation_id=self._conversation_id
        )
        return PgMemory(self._db_pool), recorder

    async def run(self) -> None:
        memory, recorder = await self._build_persistence()
        # Resolve the user's connector credentials once (e.g. a fresh Gmail OAuth
        # token), so tool dispatch is a plain sync lookup.
        creds: dict[str, dict] = {}
        if self._db_pool is not None:
            try:
                creds = await build_credentials(self._db_pool, self._settings, self._user_id)
            except Exception:
                log.exception("failed to resolve connector credentials")
        extra: dict[str, object] = {"memory": memory}
        if self._db_pool is not None:
            extra["reminder_store"] = ReminderStore(self._db_pool, self._user_id)
        catalog = ToolCatalog(
            self._registry,
            user_id=self._user_id,
            cred_lookup=lambda key: creds.get(key),
            extra=extra,
        )
        agent = AgentLoop(
            user_id=self._user_id,
            transport=self._transport,
            llm=self._build_llm(),
            catalog=catalog,
            memory=memory,
            confirm_gate=ConfirmGate(),
            recorder=recorder,
        )
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._demux())
                tg.create_task(self._transport.pump())
                tg.create_task(agent.run())
        finally:
            await self._transport.close()
            await self._end_conversation()

    async def _end_conversation(self) -> None:
        if self._db_pool is None or self._conversation_id is None:
            return
        try:
            async with self._db_pool.acquire() as conn:
                await repo.end_conversation(conn, self._conversation_id)
        except Exception:
            log.exception("failed to close conversation", extra={"user_id": self._user_id})

    async def _demux(self) -> None:
        """Translate raw WS frames into typed inbound events."""
        try:
            while True:
                msg = await self._ws_receive()
                if msg.bytes is not None:
                    # Text-only for now; keep the path for voice but ignore audio.
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
            await self._inbound.put(_CLOSE)

    def _decode(self, payload: dict[str, Any]) -> InboundEvent | None:
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
