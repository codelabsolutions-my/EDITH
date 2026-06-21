"""Endpointer (energy VAD) behaviour with synthetic PCM."""

from __future__ import annotations

import array

from app.voice.vad import Endpointer, rms

SR = 16000


def _pcm(ms: int, amplitude: int) -> bytes:
    """Generate `ms` of 16kHz mono PCM at a constant |amplitude| (square-ish)."""
    n = int(SR * ms / 1000)
    samples = array.array("h", [amplitude if i % 2 else -amplitude for i in range(n)])
    return samples.tobytes()


def silence(ms: int) -> bytes:
    return _pcm(ms, 0)


def loud(ms: int, amplitude: int = 4000) -> bytes:
    return _pcm(ms, amplitude)


def test_rms_distinguishes_silence_from_speech() -> None:
    assert rms(silence(20)) < 100
    assert rms(loud(20)) > 1000


def test_utterance_emitted_after_trailing_silence() -> None:
    ep = Endpointer(sample_rate=SR, silence_ms=300, min_speech_ms=100)
    # Some leading silence, then speech, then enough trailing silence to endpoint.
    assert ep.process(silence(100)).utterance is None
    r = ep.process(loud(400))
    assert r.speech_started is True
    assert r.utterance is None  # still talking
    result = ep.process(silence(400))
    assert result.utterance is not None
    assert len(result.utterance) > 0
    assert ep.speaking is False  # back to idle after endpointing


def test_pure_silence_never_endpoints() -> None:
    ep = Endpointer(sample_rate=SR, silence_ms=300)
    out = ep.process(silence(2000))
    assert out.speech_started is False
    assert out.utterance is None


def test_brief_blip_below_min_speech_is_not_endpointed() -> None:
    # A 40ms click followed by silence shouldn't count as an utterance.
    ep = Endpointer(sample_rate=SR, silence_ms=200, min_speech_ms=300)
    ep.process(loud(40))
    out = ep.process(silence(500))
    assert out.utterance is None


def test_speech_onset_signals_barge_in() -> None:
    ep = Endpointer(sample_rate=SR)
    assert ep.process(silence(60)).speech_started is False
    assert ep.process(loud(60)).speech_started is True


def test_reset_clears_in_progress_utterance() -> None:
    ep = Endpointer(sample_rate=SR, silence_ms=300, min_speech_ms=100)
    ep.process(loud(200))
    assert ep.speaking is True
    ep.reset()
    assert ep.speaking is False
    # After reset, trailing silence produces nothing (no buffered utterance).
    assert ep.process(silence(400)).utterance is None
