"""VoicePipeline — the voice-mode :class:`Transport`.

Same agent loop, different wire: instead of JSON text it drains mic PCM, endpoints
utterances with VAD, transcribes them (ILMU ASR) into user turns, and renders
EDITH's streamed reply to speech **per sentence** (ILMU TTS), played back-to-back.
Speech during playback is a barge-in: it cancels the turn.

Structurally it mirrors :class:`~app.voice.text_transport.TextTransport` — a ``pump``
drains the inbound queue independently of the loop so confirms and barge-in are
handled even mid-turn — and adds the audio plumbing (endpointer, ASR, TTS, sentence
chunking). JSON events go out on ``ws_send_json``; synthesized audio on
``ws_send_bytes``.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from ..config import Settings
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
from .asr import CAPTURE_SAMPLE_RATE, StreamingASR
from .text_transport import _CLOSE, WsSend
from .transport import Transport, UserTurn
from .tts import StreamingTTS, pcm_seconds
from .vad import Endpointer

log = logging.getLogger("edith.voice")

WsSendBytes = Callable[[bytes], Awaitable[None]]
# Optional metering hook: (kind, seconds) -> awaitable. kind in {"asr","tts"}.
UsageSink = Callable[[str, float], Awaitable[None]]

# Sentence boundary: terminal punctuation followed by whitespace or end-of-string.
_SENTENCE_RE = re.compile(r".+?(?:[.!?…]+(?=\s|$)|\n+)", re.DOTALL)


class VoicePipeline(Transport):
    """Voice-mode transport: PCM in → ASR → loop → TTS → PCM out, with barge-in."""

    def __init__(
        self,
        inbound: asyncio.Queue[InboundEvent | object],
        ws_send_json: WsSend,
        ws_send_bytes: WsSendBytes,
        asr: StreamingASR,
        tts: StreamingTTS,
        *,
        settings: Settings | None = None,
        usage_sink: UsageSink | None = None,
        capture_sample_rate: int = CAPTURE_SAMPLE_RATE,
    ) -> None:
        self._inbound = inbound
        self._ws_send_json = ws_send_json
        self._ws_send_bytes = ws_send_bytes
        self._asr = asr
        self._tts = tts
        self._usage_sink = usage_sink
        self._capture_rate = capture_sample_rate
        self._endpointer = Endpointer(sample_rate=capture_sample_rate)

        self._barge_in = asyncio.Event()
        self._turns: asyncio.Queue[UserTurn | object] = asyncio.Queue()
        self._pending: dict[str, asyncio.Future[bool]] = {}
        self._turn_active = False
        # Reply text buffered until a full sentence forms, then synthesized.
        self._sentence_buf = ""
        self._spoke_this_turn = False

    # ─── inbound: drain audio, endpoint, transcribe ───────────────────────

    async def pump(self) -> None:
        while True:
            item = await self._inbound.get()
            if item is _CLOSE:
                await self._turns.put(_CLOSE)
                return
            try:
                await self._handle_inbound(item)
            except Exception:
                log.exception("voice pump error")

    async def _handle_inbound(self, event: Any) -> None:
        if isinstance(event, AudioFrameIn):
            result = self._endpointer.process(event.data)
            if result.speech_started and self._turn_active:
                # The user spoke while EDITH was talking — interrupt.
                self._barge_in.set()
            if result.utterance is not None:
                await self._transcribe_and_queue(result.utterance)
        elif isinstance(event, TextIn):
            # Typed input is still accepted in voice mode (accessibility / fallback).
            if self._turn_active:
                self._barge_in.set()
            await self._turns.put(UserTurn(text=event.text, audio_present=False))
        elif isinstance(event, ConfirmReply):
            fut = self._pending.pop(event.action_id, None)
            if fut is not None and not fut.done():
                fut.set_result(event.ok)
        elif isinstance(event, BargeInHint):
            self._barge_in.set()

    async def _transcribe_and_queue(self, pcm: bytes) -> None:
        try:
            result = await self._asr.transcribe(pcm, sample_rate=self._capture_rate)
        except Exception:
            log.exception("ASR failed")
            await self.emit(ErrorEvent(code="asr_error", message="Sorry, I didn't catch that."))
            return
        await self._meter("asr", result.seconds or pcm_seconds_16k(pcm, self._capture_rate))
        if result.text.strip():
            # Show what we heard, then hand the turn to the loop.
            await self._ws_send_json(
                {"type": "transcript", "role": "user", "text": result.text, "final": True}
            )
            await self._turns.put(UserTurn(text=result.text, audio_present=True))

    async def user_turns(self) -> AsyncIterator[UserTurn]:
        while True:
            item = await self._turns.get()
            if item is _CLOSE or not isinstance(item, UserTurn):
                return
            self._barge_in = asyncio.Event()
            self._turn_active = True
            self._sentence_buf = ""
            self._spoke_this_turn = False
            yield item

    # ─── outbound: render reply to speech per sentence ────────────────────

    async def emit(self, event: OutboundEvent) -> None:
        if isinstance(event, LLMToken):
            # Mirror text to the client AND buffer it for synthesis.
            await self._ws_send_json(
                {"type": "transcript", "role": "edith", "text": event.text, "final": False}
            )
            self._sentence_buf += event.text
            await self._speak_complete_sentences()
        elif isinstance(event, TurnComplete):
            await self._flush_speech()
            self._turn_active = False
            await self._ws_send_json({"type": "turn_end"})
        else:
            await self._ws_send_json(_serialise_json(event))

    async def set_status(self, status: Status) -> None:
        if status in (Status.LISTENING, Status.IDLE):
            self._turn_active = False
        await self._ws_send_json({"type": "status", "state": status.value})

    async def request_confirm(self, action_id: str, summary: str) -> bool:
        fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._pending[action_id] = fut
        await self._ws_send_json(
            {"type": "confirm_request", "action_id": action_id, "summary": summary}
        )
        # Speak the question so a hands-free user hears it; the reply still comes as
        # a confirm frame from the client UI.
        await self._speak(summary)
        try:
            return await fut
        finally:
            self._pending.pop(action_id, None)

    def barge_in_signal(self) -> asyncio.Event:
        return self._barge_in

    async def flush_output(self) -> None:
        await self._flush_speech()

    async def close(self) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

    # ─── speech synthesis helpers ─────────────────────────────────────────

    async def _speak_complete_sentences(self) -> None:
        """Synthesize and send every complete sentence sitting in the buffer."""
        while True:
            match = _SENTENCE_RE.match(self._sentence_buf)
            if not match:
                return
            sentence = match.group(0)
            self._sentence_buf = self._sentence_buf[match.end() :]
            await self._speak(sentence)

    async def _flush_speech(self) -> None:
        """Synthesize any trailing partial sentence at end of turn."""
        tail = self._sentence_buf.strip()
        self._sentence_buf = ""
        if tail:
            await self._speak(tail)

    async def _speak(self, text: str) -> None:
        if self._barge_in.is_set() or not text.strip():
            return
        try:
            pcm = await self._tts.synthesize(text)
        except Exception:
            log.exception("TTS failed")
            return
        if not pcm or self._barge_in.is_set():
            return
        if not self._spoke_this_turn:
            self._spoke_this_turn = True
            await self._ws_send_json({"type": "status", "state": Status.SPEAKING.value})
        await self._ws_send_bytes(pcm)
        await self._meter("tts", pcm_seconds(pcm))

    async def _meter(self, kind: str, seconds: float) -> None:
        if self._usage_sink is not None and seconds > 0:
            try:
                await self._usage_sink(kind, seconds)
            except Exception:
                log.exception("usage metering failed")


def pcm_seconds_16k(pcm: bytes, sample_rate: int) -> float:
    """Fallback duration when ASR omits usage (16-bit mono)."""
    return len(pcm) / (sample_rate * 2)


def _serialise_json(event: OutboundEvent) -> dict[str, Any]:
    match event:
        case StatusEvent(state=state):
            return {"type": "status", "state": state.value}
        case Transcript(role=role, text=text, final=final):
            return {"type": "transcript", "role": role, "text": text, "final": final}
        case ConfirmRequest(action_id=action_id, summary=summary):
            return {"type": "confirm_request", "action_id": action_id, "summary": summary}
        case ToolEvent(name=name, state=state):
            return {"type": "tool_event", "name": name, "state": state}
        case ErrorEvent(code=code, message=message):
            return {"type": "error", "code": code, "message": message}
        case _:
            raise TypeError(f"voice transport cannot JSON-serialise {type(event).__name__}")
