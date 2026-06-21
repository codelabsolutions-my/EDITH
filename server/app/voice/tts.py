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


class OpenAITTS(StreamingTTS):
    """OpenAI TTS client — an escape hatch / A-B alternative to ILMU.

    Requests ``response_format=pcm``, which OpenAI returns as raw 24 kHz mono
    16-bit little-endian PCM — the same format the voice pipeline plays, so it
    drops in without any change to playback. English-centric, so it loses the
    Manglish/BM quality ILMU provides; use for comparison or as a fallback.
    """

    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OpenAITTS requires OPENAI_API_KEY")
        self._base = settings.OPENAI_API_BASE.rstrip("/")
        self._key = settings.OPENAI_API_KEY
        self._model = settings.OPENAI_TTS_MODEL
        self._voice = settings.OPENAI_TTS_VOICE
        self._transport = transport

    async def synthesize(self, text: str) -> bytes:
        text = text.strip()
        if not text:
            return b""
        payload: dict[str, Any] = {
            "model": self._model,
            "voice": self._voice,
            "input": text,
            "response_format": "pcm",  # raw 24kHz mono 16-bit LE PCM
        }
        headers = {"Authorization": f"Bearer {self._key}"}
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, transport=self._transport) as client:
            resp = await client.post(f"{self._base}/audio/speech", json=payload, headers=headers)
            resp.raise_for_status()
            return resp.content


def create_tts(settings: Settings) -> StreamingTTS:
    """Pick the TTS provider from settings (ILMU default; OpenAI when selected)."""
    if settings.TTS_PROVIDER.lower() == "openai" and settings.OPENAI_API_KEY:
        return OpenAITTS(settings)
    return IlmuTTS(settings)
