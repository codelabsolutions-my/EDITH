"""ILMU ASR/TTS client shape — offline via httpx MockTransport.

The real endpoints were validated live (24kHz PCM TTS; ASR returns text + usage);
these tests pin the client request/response handling deterministically.
"""

from __future__ import annotations

import asyncio
import wave
from io import BytesIO

import httpx
import pytest
from app.config import Settings
from app.voice.asr import IlmuASR, pcm_to_wav
from app.voice.tts import IlmuTTS, OpenAITTS, create_tts, pcm_seconds


def _settings() -> Settings:
    return Settings(ILMU_API_BASE="https://api.test/v1", ILMU_API_KEY="sk-test")


def test_pcm_to_wav_is_valid_wav() -> None:
    pcm = b"\x01\x00" * 1600  # 1600 samples
    wav = pcm_to_wav(pcm, sample_rate=16000)
    with wave.open(BytesIO(wav), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == 16000
        assert w.getnframes() == 1600


def test_asr_posts_multipart_and_parses_text_and_usage() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["ctype"] = request.headers.get("content-type", "")
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(
            200, json={"text": "  what time is it  ", "usage": {"type": "duration", "seconds": 3}}
        )

    asr = IlmuASR(_settings(), transport=httpx.MockTransport(handler))
    result = asyncio.run(asr.transcribe(b"\x00\x00" * 800, sample_rate=16000))

    assert result.text == "what time is it"  # trimmed
    assert result.seconds == 3.0
    assert seen["path"].endswith("/audio/transcriptions")
    assert "multipart/form-data" in seen["ctype"]
    assert seen["auth"] == "Bearer sk-test"


def test_tts_posts_json_and_returns_pcm() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, content=b"\x10\x00" * 2400, headers={"content-type": "audio/pcm"}
        )

    tts = IlmuTTS(_settings(), transport=httpx.MockTransport(handler))
    pcm = asyncio.run(tts.synthesize("Hello there"))

    assert pcm == b"\x10\x00" * 2400
    assert seen["path"].endswith("/audio/speech")
    assert seen["body"]["input"] == "Hello there"
    assert seen["body"]["voice"] == "voice_2"
    # 4800 bytes at 24kHz/16-bit mono = 0.1s.
    assert abs(pcm_seconds(pcm) - 0.1) < 1e-6


def test_tts_empty_text_skips_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("should not POST for empty text")

    tts = IlmuTTS(_settings(), transport=httpx.MockTransport(handler))
    assert asyncio.run(tts.synthesize("   ")) == b""


def test_clients_require_credentials() -> None:
    with pytest.raises(ValueError):
        IlmuASR(Settings(ILMU_API_BASE="", ILMU_API_KEY=""))
    with pytest.raises(ValueError):
        IlmuTTS(Settings(ILMU_API_BASE="", ILMU_API_KEY=""))
    with pytest.raises(ValueError):
        OpenAITTS(Settings(OPENAI_API_KEY=""))


def test_openai_tts_requests_pcm() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, content=b"\x10\x00" * 2400)

    tts = OpenAITTS(
        Settings(OPENAI_API_KEY="sk-openai", OPENAI_TTS_VOICE="alloy"),
        transport=httpx.MockTransport(handler),
    )
    pcm = asyncio.run(tts.synthesize("Hello"))
    assert pcm == b"\x10\x00" * 2400  # raw 24kHz PCM, same as the pipeline expects
    assert seen["path"].endswith("/audio/speech")
    assert seen["body"]["response_format"] == "pcm"
    assert seen["body"]["voice"] == "alloy"
    assert seen["auth"] == "Bearer sk-openai"


def test_create_tts_selects_provider() -> None:
    ilmu = Settings(ILMU_API_BASE="https://api.test/v1", ILMU_API_KEY="sk-ilmu")
    assert isinstance(create_tts(ilmu), IlmuTTS)
    openai = Settings(
        ILMU_API_BASE="https://api.test/v1",
        ILMU_API_KEY="sk-ilmu",
        TTS_PROVIDER="openai",
        OPENAI_API_KEY="sk-openai",
    )
    assert isinstance(create_tts(openai), OpenAITTS)
    # openai selected but no key -> falls back to ILMU.
    no_key = Settings(
        ILMU_API_BASE="https://api.test/v1", ILMU_API_KEY="sk-ilmu", TTS_PROVIDER="openai"
    )
    assert isinstance(create_tts(no_key), IlmuTTS)
