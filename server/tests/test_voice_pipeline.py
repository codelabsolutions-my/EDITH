"""VoicePipeline: audio→ASR→turn, reply→sentence→TTS, and barge-in — with fakes."""

from __future__ import annotations

import array
import asyncio

from app.events import AudioFrameIn, LLMToken, Status, ToolEvent, TurnComplete
from app.voice.asr import StreamingASR, Transcription
from app.voice.pipeline import VoicePipeline
from app.voice.text_transport import _CLOSE
from app.voice.tts import StreamingTTS

SR = 16000


def _pcm(ms: int, amplitude: int) -> bytes:
    n = int(SR * ms / 1000)
    return array.array("h", [amplitude if i % 2 else -amplitude for i in range(n)]).tobytes()


class FakeASR(StreamingASR):
    def __init__(self, text: str = "what time is it") -> None:
        self.text = text
        self.calls = 0

    async def transcribe(self, pcm: bytes, *, sample_rate: int = SR) -> Transcription:
        self.calls += 1
        return Transcription(text=self.text, seconds=1.5)


class FakeTTS(StreamingTTS):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def synthesize(self, text: str) -> bytes:
        self.calls.append(text)
        return b"\x00\x01" * 100  # stand-in PCM


def _pipeline() -> tuple[VoicePipeline, asyncio.Queue, list, list, FakeASR, FakeTTS]:
    inbound: asyncio.Queue = asyncio.Queue()
    sent_json: list = []
    sent_bytes: list = []

    async def send_json(msg: dict) -> None:
        sent_json.append(msg)

    async def send_bytes(data: bytes) -> None:
        sent_bytes.append(data)

    asr, tts = FakeASR(), FakeTTS()
    vp = VoicePipeline(inbound, send_json, send_bytes, asr, tts)
    return vp, inbound, sent_json, sent_bytes, asr, tts


def test_audio_endpoints_to_a_transcribed_user_turn() -> None:
    async def scenario() -> None:
        vp, inbound, sent_json, _b, asr, _t = _pipeline()
        # Speech then >700ms silence endpoints the utterance.
        await inbound.put(AudioFrameIn(data=_pcm(400, 4000)))
        await inbound.put(AudioFrameIn(data=_pcm(800, 0)))
        await inbound.put(_CLOSE)

        pump = asyncio.create_task(vp.pump())
        turns = [t async for t in vp.user_turns()]
        await pump

        assert asr.calls == 1
        assert len(turns) == 1
        assert turns[0].text == "what time is it"
        assert turns[0].audio_present is True
        # The recognised user text was mirrored to the client.
        assert any(m.get("type") == "transcript" and m.get("role") == "user" for m in sent_json)

    asyncio.run(scenario())


def test_reply_is_synthesized_per_sentence_then_turn_ends() -> None:
    async def scenario() -> None:
        vp, _q, sent_json, sent_bytes, _a, tts = _pipeline()
        vp._turn_active = True  # simulate an active turn

        await vp.emit(LLMToken(text="Hello there. How "))
        await vp.emit(LLMToken(text="are you?"))
        await vp.emit(TurnComplete())

        # Two complete sentences -> two TTS calls -> two audio frames out.
        assert [c.strip() for c in tts.calls] == ["Hello there.", "How are you?"]
        assert len(sent_bytes) == 2
        # SPEAKING announced before the first audio; turn_end closes the turn.
        assert {"type": "status", "state": Status.SPEAKING.value} in sent_json
        assert {"type": "turn_end"} in sent_json

    asyncio.run(scenario())


def test_trailing_partial_sentence_is_flushed_on_turn_end() -> None:
    async def scenario() -> None:
        vp, _q, _j, _b, _a, tts = _pipeline()
        vp._turn_active = True
        await vp.emit(LLMToken(text="no terminal punctuation here"))
        await vp.emit(TurnComplete())
        assert [c.strip() for c in tts.calls] == ["no terminal punctuation here"]

    asyncio.run(scenario())


def test_speech_during_playback_triggers_barge_in() -> None:
    async def scenario() -> None:
        vp, _q, _j, _b, _a, _t = _pipeline()
        vp._turn_active = True
        assert vp.barge_in_signal().is_set() is False
        # Speech onset while a turn is active = barge-in.
        await vp._handle_inbound(AudioFrameIn(data=_pcm(120, 4000)))
        assert vp.barge_in_signal().is_set() is True

    asyncio.run(scenario())


def test_no_tts_after_barge_in() -> None:
    async def scenario() -> None:
        vp, _q, _j, sent_bytes, _a, tts = _pipeline()
        vp._turn_active = True
        vp.barge_in_signal().set()
        await vp.emit(LLMToken(text="This should not be spoken."))
        assert tts.calls == []
        assert sent_bytes == []

    asyncio.run(scenario())


def test_non_audio_events_serialize_to_json() -> None:
    async def scenario() -> None:
        vp, _q, sent_json, _b, _a, _t = _pipeline()
        await vp.emit(ToolEvent(name="current_time", state="running"))
        assert {"type": "tool_event", "name": "current_time", "state": "running"} in sent_json

    asyncio.run(scenario())
