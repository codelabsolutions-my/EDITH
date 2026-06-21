import 'dart:async';
import 'dart:typed_data';

import '../audio_io.dart';

/// Placeholder capture for non-web platforms.
///
/// Web is the priority target; Android/iOS will get a native PCM source later
/// (the `record` package's stream API or a platform channel). Until then these
/// throw on [start] so the failure is loud rather than silent.
class StubAudioCapture implements AudioCapture {
  final _frames = StreamController<Uint8List>.broadcast();

  @override
  Stream<Uint8List> get frames => _frames.stream;

  @override
  Future<bool> hasPermission() async => false;

  @override
  Future<void> start() async {
    throw const AudioException(
      'voice capture is not yet implemented on this platform (web only)',
    );
  }

  @override
  Future<void> stop() async {}

  @override
  Future<void> dispose() async {
    await _frames.close();
  }
}

/// Placeholder playback for non-web platforms.
class StubAudioPlayback implements AudioPlayback {
  final _level = StreamController<double>.broadcast();

  @override
  Future<void> prime() async {}

  @override
  void enqueue(Uint8List pcm) {}

  @override
  void stop() {}

  @override
  Stream<double> get level => _level.stream;

  @override
  Future<void> dispose() async {
    await _level.close();
  }
}

AudioCapture createCapture() => StubAudioCapture();
AudioPlayback createPlayback() => StubAudioPlayback();
