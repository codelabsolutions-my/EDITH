import 'dart:typed_data';

/// Target audio formats fixed by the server contract.
class AudioFormat {
  const AudioFormat._();

  /// Mic capture: 16 kHz mono 16-bit signed LE PCM.
  static const int captureSampleRate = 16000;

  /// Playback: 24 kHz mono 16-bit signed LE PCM.
  static const int playbackSampleRate = 24000;

  static const int channels = 1;
}

/// Captures microphone audio and emits 16 kHz mono 16-bit PCM frames.
///
/// Implementations resample from whatever the browser/OS provides down to
/// [AudioFormat.captureSampleRate]. The UI/controller depends only on this
/// interface, so tests inject a fake source.
abstract class AudioCapture {
  /// Whether mic permission has been granted (best-effort; may be unknown
  /// until [start] is called on some platforms).
  Future<bool> hasPermission();

  /// Start capturing. Emits frames on [frames]. Throws [AudioException] if the
  /// mic is unavailable or permission is denied.
  Future<void> start();

  /// Stop capturing and release the mic.
  Future<void> stop();

  /// Stream of ready-to-send PCM frames (16 kHz mono 16-bit LE).
  Stream<Uint8List> get frames;

  Future<void> dispose();
}

/// Plays a continuous stream of 24 kHz mono 16-bit PCM frames back-to-back.
abstract class AudioPlayback {
  /// Enqueue a frame for playback.
  void enqueue(Uint8List pcm);

  /// Immediately stop and drop all queued/playing audio (barge-in).
  void stop();

  /// Most recent output amplitude (0..1) for the reactive visual.
  Stream<double> get level;

  Future<void> dispose();
}

/// Raised when audio hardware is unavailable or permission is denied.
class AudioException implements Exception {
  const AudioException(this.message);

  final String message;

  @override
  String toString() => 'AudioException: $message';
}
