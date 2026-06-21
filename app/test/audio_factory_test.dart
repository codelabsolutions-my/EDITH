import 'package:edith_app/voice/audio_factory.dart';
import 'package:edith_app/voice/audio_io.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  // Constructing the native recorder/player touches plugin method channels.
  // Stub them so we can assert the factory wires up the right interface types
  // without a real device. (Web vs native *selection* is a compile-time
  // conditional import, already proven by both `build web` and `build apk`.)
  TestWidgetsFlutterBinding.ensureInitialized();

  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  setUp(() {
    messenger.setMockMethodCallHandler(
      const MethodChannel('com.llfbandit.record/messages'),
      (call) async => null,
    );
  });

  tearDown(() {
    messenger.setMockMethodCallHandler(
      const MethodChannel('com.llfbandit.record/messages'),
      null,
    );
  });

  test('createAudioCapture returns an AudioCapture', () {
    expect(createAudioCapture(), isA<AudioCapture>());
  });

  test('createAudioPlayback returns an AudioPlayback', () {
    expect(createAudioPlayback(), isA<AudioPlayback>());
  });
}
