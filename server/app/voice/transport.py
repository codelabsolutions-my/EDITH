"""The Transport seam — the single boundary between the agent loop and the wire.

The :class:`~app.agent.loop.AgentLoop` talks only to a :class:`Transport`. A text
chat box (:class:`~app.voice.text_transport.TextTransport`, M0) and the future
voice pipeline (M2) are interchangeable behind this ABC, so confirmation,
barge-in, tool dispatch and memory are written exactly once.
"""

from __future__ import annotations

import abc
import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from ..events import OutboundEvent, Status


@dataclass(frozen=True)
class UserTurn:
    """One unit of user input handed to the agent loop.

    ``audio_present`` lets the loop know a turn came from speech (voice mode);
    in M0 it is always ``False``.
    """

    text: str
    audio_present: bool


class Transport(abc.ABC):
    """Abstract transport — the seam the agent loop drives."""

    @abc.abstractmethod
    def user_turns(self) -> AsyncIterator[UserTurn]:
        """Yield one :class:`UserTurn` per user input, until the session ends."""
        raise NotImplementedError

    @abc.abstractmethod
    async def emit(self, event: OutboundEvent) -> None:
        """Send an outbound event to the client."""
        raise NotImplementedError

    @abc.abstractmethod
    async def set_status(self, status: Status) -> None:
        """Update the agent status (drives a spinner in text, the orb in voice)."""
        raise NotImplementedError

    @abc.abstractmethod
    async def request_confirm(self, action_id: str, summary: str) -> bool:
        """Emit a ConfirmRequest and block until the matching reply arrives."""
        raise NotImplementedError

    @abc.abstractmethod
    def barge_in_signal(self) -> asyncio.Event:
        """Return the event that is set when the user interrupts mid-turn."""
        raise NotImplementedError

    @abc.abstractmethod
    async def flush_output(self) -> None:
        """Flush any buffered output to the client (e.g. drain TTS in voice)."""
        raise NotImplementedError

    @abc.abstractmethod
    async def close(self) -> None:
        """Release transport resources."""
        raise NotImplementedError
