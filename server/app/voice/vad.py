"""Voice activity detection + utterance endpointing.

Turns a continuous stream of mic PCM into discrete utterances: detect speech
onset, collect until trailing silence, then emit the buffered utterance for batch
ASR. The same onset signal drives **barge-in** — speech while EDITH is talking
cancels playback.

This baseline uses a simple RMS energy threshold with a silence hangover. It is
deterministic and dependency-free (``audioop`` was removed in Python 3.13). The
:class:`Endpointer` is model-agnostic; a Silero/webrtcvad frame classifier can drop
in behind :meth:`Endpointer._is_speech` later (ADR 0002 names Silero) without
changing the pipeline.
"""

from __future__ import annotations

import array
import math
from dataclasses import dataclass

DEFAULT_SAMPLE_RATE = 16000


@dataclass(frozen=True)
class EndpointResult:
    """What :meth:`Endpointer.process` observed for the bytes just fed in."""

    speech_started: bool  # a speech onset occurred in this call (drives barge-in)
    utterance: bytes | None  # a complete utterance ended in this call (send to ASR)


def rms(frame: bytes) -> float:
    """Root-mean-square amplitude of 16-bit little-endian mono PCM."""
    if len(frame) < 2:
        return 0.0
    samples = array.array("h")
    samples.frombytes(frame[: len(frame) - (len(frame) % 2)])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


class Endpointer:
    """Energy-based utterance endpointer fed arbitrary-sized PCM chunks.

    Feed PCM with :meth:`process`; it buffers a frame at a time. After speech of at
    least ``min_speech_ms`` followed by ``silence_ms`` of trailing silence, it
    returns the utterance (with a short pre-roll so the onset isn't clipped).
    """

    def __init__(
        self,
        *,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        frame_ms: int = 20,
        silence_ms: int = 700,
        min_speech_ms: int = 200,
        energy_threshold: float = 500.0,
        preroll_ms: int = 200,
    ) -> None:
        self._sample_rate = sample_rate
        self._frame_ms = frame_ms
        self._frame_bytes = int(sample_rate * frame_ms / 1000) * 2
        self._silence_ms = silence_ms
        self._min_speech_ms = min_speech_ms
        self._threshold = energy_threshold
        self._preroll_frames = max(1, preroll_ms // frame_ms)

        self._leftover = bytearray()
        self._speaking = False
        self._utterance = bytearray()
        self._speech_ms = 0
        self._silence_run_ms = 0
        self._preroll: list[bytes] = []

    @property
    def speaking(self) -> bool:
        return self._speaking

    def reset(self) -> None:
        """Drop any in-progress utterance and pre-roll (e.g. after a barge-in)."""
        self._leftover.clear()
        self._speaking = False
        self._utterance.clear()
        self._speech_ms = 0
        self._silence_run_ms = 0
        self._preroll.clear()

    def _is_speech(self, frame: bytes) -> bool:
        return rms(frame) >= self._threshold

    def process(self, pcm: bytes) -> EndpointResult:
        self._leftover.extend(pcm)
        started = False
        finished: bytes | None = None

        while len(self._leftover) >= self._frame_bytes:
            frame = bytes(self._leftover[: self._frame_bytes])
            del self._leftover[: self._frame_bytes]
            speech = self._is_speech(frame)

            if not self._speaking:
                # Keep a rolling pre-roll so we don't clip the start of speech.
                self._preroll.append(frame)
                if len(self._preroll) > self._preroll_frames:
                    self._preroll.pop(0)
                if speech:
                    self._speaking = True
                    started = True
                    self._utterance = bytearray(b"".join(self._preroll))
                    self._preroll.clear()
                    self._speech_ms = self._frame_ms
                    self._silence_run_ms = 0
                continue

            # Speaking: keep collecting and track trailing silence.
            self._utterance.extend(frame)
            if speech:
                self._speech_ms += self._frame_ms
                self._silence_run_ms = 0
            else:
                self._silence_run_ms += self._frame_ms
                if (
                    self._silence_run_ms >= self._silence_ms
                    and self._speech_ms >= self._min_speech_ms
                ):
                    finished = bytes(self._utterance)
                    self._utterance = bytearray()
                    self._speaking = False
                    self._speech_ms = 0
                    self._silence_run_ms = 0
                    self._preroll.clear()
                    break

        return EndpointResult(speech_started=started, utterance=finished)
