import 'dart:async';
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

import '../audio_io.dart';
import '../pcm.dart';

/// Streaming PCM playback on Flutter web via the Web Audio API.
///
/// Each inbound 24 kHz PCM frame is decoded to an [web.AudioBuffer] and
/// scheduled on an [web.AudioBufferSourceNode] back-to-back using a running
/// playhead so frames play gaplessly as they arrive. [stop] cancels everything
/// for barge-in.
class WebAudioPlayback implements AudioPlayback {
  WebAudioPlayback();

  web.AudioContext? _ctx;
  final List<web.AudioBufferSourceNode> _sources = [];

  /// The time (in the AudioContext clock) at which the next frame should start.
  double _playhead = 0;

  final _level = StreamController<double>.broadcast();

  web.AudioContext _context() {
    final existing = _ctx;
    if (existing != null) {
      return existing;
    }
    final ctx = web.AudioContext();
    _ctx = ctx;
    ctx.resume();
    return ctx;
  }

  @override
  Future<void> prime() async {
    // MUST be called from a user gesture (the "tap to talk" handler). A context
    // created lazily on the first inbound frame is outside a gesture and stays
    // suspended → silent. Creating + resuming it here, and playing one silent
    // buffer, unlocks autoplay so EDITH's reply actually plays.
    final ctx = _context();
    try {
      await ctx.resume().toDart;
    } catch (_) {
      // resume can reject if already running; ignore.
    }
    final silent = ctx.createBuffer(AudioFormat.channels, 1, AudioFormat.playbackSampleRate);
    final source = ctx.createBufferSource();
    source.buffer = silent;
    source.connect(ctx.destination);
    source.start();
    _playhead = ctx.currentTime;
  }

  @override
  void enqueue(Uint8List pcm) {
    if (pcm.isEmpty) {
      return;
    }
    final ctx = _context();
    final floats = Pcm.int16ToFloats(pcm);
    if (floats.isEmpty) {
      return;
    }

    final buffer = ctx.createBuffer(
      AudioFormat.channels,
      floats.length,
      AudioFormat.playbackSampleRate,
    );
    // copyToChannel wants a Float32List view.
    buffer.copyToChannel(floats.toJS, 0);

    final source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    final now = ctx.currentTime;
    // If the playhead has fallen behind real time, restart from now.
    final startAt = _playhead > now ? _playhead : now;
    source.start(startAt);
    _playhead = startAt + buffer.duration;

    _sources.add(source);
    source.onended = (web.Event _) {
      _sources.remove(source);
    }.toJS;

    _level.add(Pcm.rms16(pcm).clamp(0.0, 1.0));
  }

  @override
  void stop() {
    for (final source in _sources) {
      try {
        source.stop();
        source.disconnect();
      } catch (_) {
        // Already stopped/ended.
      }
    }
    _sources.clear();
    _playhead = _ctx?.currentTime ?? 0;
    _level.add(0);
  }

  @override
  Stream<double> get level => _level.stream;

  @override
  Future<void> dispose() async {
    stop();
    await _ctx?.close().toDart;
    _ctx = null;
    await _level.close();
  }
}

AudioPlayback createPlayback() => WebAudioPlayback();
