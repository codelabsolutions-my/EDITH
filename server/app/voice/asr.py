"""Speech-to-text over ILMU's batch ASR (OpenAI-compatible ``/audio/transcriptions``).

ILMU ASR is file/batch, not streaming (ADR 0002). The :class:`StreamingASR` seam
names the *role* — the voice pipeline endpoints an utterance with VAD and hands the
whole PCM buffer here for one transcription. We wrap raw 16-bit mono PCM in a WAV
container (the endpoint wants a real audio file) and return the transcript plus the
billed duration (``usage.seconds``) for voice-seconds metering.
"""

from __future__ import annotations

import abc
import io
import wave
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import Settings

# The mic capture rate the client streams at (see the audio contract).
CAPTURE_SAMPLE_RATE = 16000
_REQUEST_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


@dataclass(frozen=True)
class Transcription:
    """The result of transcribing one utterance."""

    text: str
    seconds: float  # billed audio duration, for usage metering


class StreamingASR(abc.ABC):
    """Speech-to-text seam — one utterance of PCM in, transcript out."""

    @abc.abstractmethod
    async def transcribe(
        self, pcm: bytes, *, sample_rate: int = CAPTURE_SAMPLE_RATE
    ) -> Transcription:
        """Transcribe 16-bit mono PCM. ``sample_rate`` is the PCM's rate."""
        raise NotImplementedError


class IlmuASR(StreamingASR):
    """ILMU batch ASR client."""

    def __init__(
        self,
        settings: Settings,
        *,
        model: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not settings.ILMU_API_BASE or not settings.ILMU_API_KEY:
            raise ValueError("IlmuASR requires ILMU_API_BASE and ILMU_API_KEY")
        self._base = settings.ILMU_API_BASE.rstrip("/")
        self._key = settings.ILMU_API_KEY
        self._model = model or settings.ILMU_ASR_MODEL or "ilmu-asr-v4.2"
        self._transport = transport

    async def transcribe(
        self, pcm: bytes, *, sample_rate: int = CAPTURE_SAMPLE_RATE
    ) -> Transcription:
        wav = pcm_to_wav(pcm, sample_rate=sample_rate)
        files = {"file": ("utterance.wav", wav, "audio/wav")}
        data = {"model": self._model}
        headers = {"Authorization": f"Bearer {self._key}"}
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, transport=self._transport) as client:
            resp = await client.post(
                f"{self._base}/audio/transcriptions", files=files, data=data, headers=headers
            )
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()
        usage = body.get("usage") or {}
        return Transcription(
            text=str(body.get("text", "")).strip(),
            seconds=float(usage.get("seconds", 0.0)),
        )


def pcm_to_wav(pcm: bytes, *, sample_rate: int, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw little-endian PCM in a minimal WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()
