"""The typed event vocabulary that flows between the wire and the agent loop.

Text and voice are the same agent loop; the only thing that differs is the
:class:`~app.voice.transport.Transport`. To make that possible, data flows as
**typed events**, never raw bytes: a text client produces a :class:`TextIn`, the
future voice pipeline produces the same from ILMU ASR, and the orchestrator
(:class:`~app.agent.loop.AgentLoop`) cannot tell the two apart.

All events are frozen dataclasses. ``InboundEvent`` flows client -> loop;
``OutboundEvent`` flows loop -> client.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    """The agent's turn state — drives the orb (voice) or a spinner (text)."""

    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    IDLE = "idle"


# ─── Inbound (client -> loop) ─────────────────────────────────────────────


@dataclass(frozen=True)
class AudioFrameIn:
    """A frame of raw mic audio. Ignored in M0 (text-only)."""

    data: bytes


@dataclass(frozen=True)
class TextIn:
    """A line of typed user input — a first-class turn trigger."""

    text: str


@dataclass(frozen=True)
class ConfirmReply:
    """The user's answer to a pending :class:`ConfirmRequest`."""

    action_id: str
    ok: bool


@dataclass(frozen=True)
class BargeInHint:
    """A client-side hint that the user interrupted (client VAD fired first)."""


InboundEvent = AudioFrameIn | TextIn | ConfirmReply | BargeInHint


# ─── Outbound (loop -> client) ────────────────────────────────────────────


@dataclass(frozen=True)
class StatusEvent:
    """The agent's current :class:`Status`."""

    state: Status


@dataclass(frozen=True)
class Transcript:
    """A line of the live transcript, for either side of the conversation."""

    role: str  # "user" | "edith"
    text: str
    final: bool


@dataclass(frozen=True)
class LLMToken:
    """One streamed chunk of EDITH's reply (rendered as a non-final transcript)."""

    text: str


@dataclass(frozen=True)
class AudioFrameOut:
    """A frame of EDITH's streamed speech. Voice only (unused in M0)."""

    data: bytes


@dataclass(frozen=True)
class ConfirmRequest:
    """A request for the user to confirm a ``CONFIRM`` tool before it runs."""

    action_id: str
    summary: str


@dataclass(frozen=True)
class ToolEvent:
    """A UI hint about a tool's lifecycle. ``state`` in {running, done, error}."""

    name: str
    state: str


@dataclass(frozen=True)
class ErrorEvent:
    """A user-facing error (fail graceful — never a stack trace)."""

    code: str
    message: str


@dataclass(frozen=True)
class TurnComplete:
    """The turn finished; text clients re-enable input on this."""


OutboundEvent = (
    StatusEvent
    | Transcript
    | LLMToken
    | AudioFrameOut
    | ConfirmRequest
    | ToolEvent
    | ErrorEvent
    | TurnComplete
)
