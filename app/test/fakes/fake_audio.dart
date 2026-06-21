import 'dart:async';
import 'dart:typed_data';

import 'package:edith_app/voice/audio_io.dart';

/// Controllable fake mic: tests push frames and decide whether [start] throws.
class FakeAudioCapture implements AudioCapture {
  FakeAudioCapture({this.startThrows});

  /// If set, [start] throws this instead of starting.
  final AudioException? startThrows;

  final _frames = StreamController<Uint8List>.broadcast();
  bool started = false;
  bool stopped = false;
  bool disposed = false;

  /// Simulate the mic producing a captured frame.
  void emit(Uint8List frame) => _frames.add(frame);

  @override
  Stream<Uint8List> get frames => _frames.stream;

  @override
  Future<bool> hasPermission() async => true;

  @override
  Future<void> start() async {
    if (startThrows != null) {
      throw startThrows!;
    }
    started = true;
  }

  @override
  Future<void> stop() async {
    stopped = true;
  }

  @override
  Future<void> dispose() async {
    disposed = true;
    await _frames.close();
  }
}

/// Records enqueued frames and stop() calls; emits levels on demand.
class FakeAudioPlayback implements AudioPlayback {
  final List<Uint8List> enqueued = [];
  int stopCount = 0;
  bool disposed = false;
  final _level = StreamController<double>.broadcast();

  void emitLevel(double v) => _level.add(v);

  @override
  void enqueue(Uint8List pcm) => enqueued.add(pcm);

  @override
  void stop() => stopCount++;

  @override
  Stream<double> get level => _level.stream;

  @override
  Future<void> dispose() async {
    disposed = true;
    await _level.close();
  }
}
