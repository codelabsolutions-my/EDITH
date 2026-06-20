"""Transport seam between the agent loop and the wire.

M0 ships :class:`~app.voice.text_transport.TextTransport` only. The voice
pipeline (VAD -> ASR -> loop -> TTS, with barge-in) lands in M2 against the same
:class:`~app.voice.transport.Transport` ABC — the agent loop does not change.
"""

from __future__ import annotations

from .transport import Transport, UserTurn

__all__ = ["Transport", "UserTurn"]
