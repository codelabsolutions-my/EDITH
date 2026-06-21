import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_sound/flutter_sound.dart';

import '../audio_io.dart';
import '../pcm.dart';

/// Native streaming PCM playback (Android/iOS/desktop) via flutter_sound's
/// `startPlayerFromStream`, fed a live stream of raw 24 kHz PCM16 frames.
///
/// flutter_sound owns the buffering/scheduling so frames play back-to-back as
/// they arrive; [stop] flushes the player for barge-in.
class NativeAudioPlayback implements AudioPlayback {
  NativeAudioPlayback({FlutterSoundPlayer? player})
      : _player = player ?? FlutterSoundPlayer();

  final FlutterSoundPlayer _player;
  final _level = StreamController<double>.broadcast();
  bool _started = false;
  bool _starting = false;
  final List<Uint8List> _pending = [];

  Future<void> _ensureStarted() async {
    if (_started || _starting) {
      return;
    }
    _starting = true;
    await _player.openPlayer();
    await _player.startPlayerFromStream(
      codec: Codec.pcm16,
      numChannels: AudioFormat.channels,
      sampleRate: AudioFormat.playbackSampleRate,
      interleaved: true,
      // ~21 ms at 24 kHz mono 16-bit; small enough for low-latency back-to-back
      // playback, large enough to avoid underflow churn.
      bufferSize: 1024,
    );
    _started = true;
    _starting = false;
    // Flush anything enqueued during startup.
    final pending = List<Uint8List>.from(_pending);
    _pending.clear();
    for (final pcm in pending) {
      _feed(pcm);
    }
  }

  @override
  void enqueue(Uint8List pcm) {
    if (pcm.isEmpty) {
      return;
    }
    _level.add(Pcm.rms16(pcm).clamp(0.0, 1.0));
    if (_started) {
      _feed(pcm);
    } else {
      _pending.add(pcm);
      unawaited(_ensureStarted());
    }
  }

  void _feed(Uint8List pcm) {
    // feedUint8FromStream applies backpressure; fire-and-forget is fine for
    // back-to-back playback.
    unawaited(_player.feedUint8FromStream(pcm));
  }

  @override
  void stop() {
    _pending.clear();
    _level.add(0);
    if (_started) {
      // Stop and reopen the stream so the next turn starts clean (barge-in).
      unawaited(_restart());
    }
  }

  Future<void> _restart() async {
    _started = false;
    try {
      await _player.stopPlayer();
    } catch (_) {
      // Already stopped.
    }
  }

  @override
  Stream<double> get level => _level.stream;

  @override
  Future<void> dispose() async {
    _pending.clear();
    try {
      await _player.stopPlayer();
      await _player.closePlayer();
    } catch (_) {
      // Best effort.
    }
    await _level.close();
  }
}
