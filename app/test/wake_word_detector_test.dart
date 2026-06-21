import 'package:edith_app/wakeword/wake_word_detector.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('DisabledWakeWordDetector', () {
    test('is disabled and never fires a detection', () async {
      final detector = DisabledWakeWordDetector();
      addTearDown(detector.dispose);

      expect(detector.isEnabled, isFalse);

      var fired = false;
      final sub = detector.detections.listen((_) => fired = true);

      await detector.start();
      await Future<void>.delayed(const Duration(milliseconds: 10));
      await detector.stop();

      expect(fired, isFalse);
      await sub.cancel();
    });

    test('start/stop/dispose are safe no-ops', () async {
      final detector = DisabledWakeWordDetector();
      await detector.start();
      await detector.stop();
      await detector.dispose();
      // Disposing twice should not throw.
      await detector.dispose();
    });
  });
}
