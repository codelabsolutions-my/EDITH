import 'dart:async';

/// On-device wake-word ("ambient invocation") detection.
///
/// Pluggable so a real engine (e.g. Porcupine) can drop in behind this
/// interface. A real engine needs an access key, so the **default is a disabled
/// stub** — no keys are hardcoded. When [isEnabled] is false the app simply
/// doesn't offer hands-free start.
abstract class WakeWordDetector {
  /// Whether a usable engine is configured. False for the stub.
  bool get isEnabled;

  /// Fires each time the wake word is detected while [start]ed.
  Stream<void> get detections;

  /// Begin listening for the wake word. No-op (and never fires) when disabled.
  Future<void> start();

  /// Stop listening.
  Future<void> stop();

  Future<void> dispose();
}

/// The default detector: explicitly disabled until a real engine + key are
/// wired in. Surfaces a clear state rather than pretending to listen.
class DisabledWakeWordDetector implements WakeWordDetector {
  DisabledWakeWordDetector();

  final _controller = StreamController<void>.broadcast();

  @override
  bool get isEnabled => false;

  @override
  Stream<void> get detections => _controller.stream;

  @override
  Future<void> start() async {
    // Intentionally inert: no key/engine configured.
  }

  @override
  Future<void> stop() async {}

  @override
  Future<void> dispose() async {
    await _controller.close();
  }
}
