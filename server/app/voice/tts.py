"""Text-to-speech over ILMU's batch TTS (OpenAI-compatible ``/audio/speech``).

ILMU TTS returns **raw 16-bit mono PCM at 24 kHz** (no WAV header). The voice
pipeline synthesises **per sentence** and plays the chunks back-to-back, so first
audio arrives ~one sentence after the LLM starts — the pseudo-streaming that hides
the batch reality (ADR 0002).
"""

from __future__ import annotations

import abc
from typing import Any

import httpx

from ..config import Settings

# ILMU TTS output format (validated against the live API).
OUTPUT_SAMPLE_RATE = 24000
OUTPUT_SAMPLE_WIDTH = 2  # bytes (16-bit)
_REQUEST_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


def pcm_seconds(pcm: bytes) -> float:
    """Duration of 24kHz mono 16-bit PCM, for usage metering."""
    return len(pcm) / (OUTPUT_SAMPLE_RATE * OUTPUT_SAMPLE_WIDTH)


class StreamingTTS(abc.ABC):
    """Text-to-speech seam — one sentence in, a PCM buffer out."""

    @abc.abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Synthesise ``text`` to 24kHz mono 16-bit PCM bytes."""
        raise NotImplementedError


class IlmuTTS(StreamingTTS):
    """ILMU batch TTS client."""

    def __init__(
        self,
        settings: Settings,
        *,
        model: str | None = None,
        voice: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not settings.ILMU_API_BASE or not settings.ILMU_API_KEY:
            raise ValueError("IlmuTTS requires ILMU_API_BASE and ILMU_API_KEY")
        self._base = settings.ILMU_API_BASE.rstrip("/")
        self._key = settings.ILMU_API_KEY
        self._model = model or settings.ILMU_TTS_MODEL or "ilmu-tts-v2"
        self._voice = voice or settings.ILMU_TTS_VOICE or "voice_2"
        self._transport = transport

    async def synthesize(self, text: str) -> bytes:
        text = text.strip()
        if not text:
            return b""
        payload: dict[str, Any] = {"model": self._model, "voice": self._voice, "input": text}
        headers = {"Authorization": f"Bearer {self._key}"}
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, transport=self._transport) as client:
            resp = await client.post(f"{self._base}/audio/speech", json=payload, headers=headers)
            resp.raise_for_status()
            return resp.content
