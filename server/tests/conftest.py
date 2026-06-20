"""Shared test fixtures and the in-memory fake transport.

Tests drive async code with ``asyncio.run(...)`` directly (no pytest-asyncio).
The :class:`RecordingTransport` records every outbound event so tests can assert
on the wire-level behaviour the agent loop produces.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.events import ConfirmRequest, OutboundEvent, Status
from app.voice.transport import Transport, UserTurn


class RecordingTransport(Transport):
    """A Transport that yields scripted turns and records emitted events.

    ``confirm_answers`` maps an ``action_id`` to the boolean reply to give when the
    loop requests confirmation; a missing id defaults to ``True``.
    """

    def __init__(
        self,
        turns: list[str],
        *,
        confirm_answers: dict[str, bool] | None = None,
    ) -> None:
        self._turns = list(turns)
        self._confirm_answers = confirm_answers or {}
        self.events: list[OutboundEvent] = []
        self.statuses: list[Status] = []
        self.confirm_requests: list[tuple[str, str]] = []
        self._barge_in = asyncio.Event()

    async def user_turns(self) -> AsyncIterator[UserTurn]:
        for text in self._turns:
            yield UserTurn(text=text, audio_present=False)

    async def emit(self, event: OutboundEvent) -> None:
        self.events.append(event)

    async def set_status(self, status: Status) -> None:
        self.statuses.append(status)

    async def request_confirm(self, action_id: str, summary: str) -> bool:
        self.confirm_requests.append((action_id, summary))
        await self.emit(ConfirmRequest(action_id=action_id, summary=summary))
        return self._confirm_answers.get(action_id, True)

    def barge_in_signal(self) -> asyncio.Event:
        return self._barge_in

    async def flush_output(self) -> None:
        return None

    async def close(self) -> None:
        return None
