import 'package:edith_app/providers.dart';
import 'package:edith_app/ui/voice_screen.dart';
import 'package:edith_app/voice/audio_io.dart';
import 'package:edith_app/voice/voice_controller.dart';
import 'package:edith_app/ws/ws_transport.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes/fake_audio.dart';
import 'ws_transport_test.dart' show FakeWebSocketChannel;

/// Drives the real VoiceScreen widget tree with fake audio + a fake socket, so
/// the voice-first landing, the gesture-to-start, and the denied path are
/// exercised against the actual widgets (no real mic/server).
void main() {
  late FakeAudioCapture capture;
  late FakeAudioPlayback playback;
  late WsTransport transport;

  ProviderScope harness({AudioException? micThrows}) {
    capture = FakeAudioCapture(startThrows: micThrows);
    playback = FakeAudioPlayback();
    transport = WsTransport(channelFactory: (_) => FakeWebSocketChannel());
    return ProviderScope(
      overrides: [
        wsTransportProvider.overrideWithValue(transport),
        voiceControllerProvider.overrideWith(
          () => VoiceController(
            captureOverride: capture,
            playbackOverride: playback,
            transportOverride: transport,
          ),
        ),
        // A token must be present for _startVoice to proceed.
        accessTokenProvider.overrideWith(_SeededToken.new),
      ],
      child: const MaterialApp(home: VoiceScreen()),
    );
  }

  testWidgets('lands voice-first with the orb and a Tap to talk affordance', (
    tester,
  ) async {
    await tester.pumpWidget(harness());
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('Tap to talk'), findsWidgets);
    expect(find.text('Type instead'), findsOneWidget);
    // Text composer is secondary — not shown until requested.
    expect(find.byType(TextField), findsNothing);
  });

  testWidgets('tap to talk starts the mic and shows Stop', (tester) async {
    await tester.pumpWidget(harness());
    await tester.pump(const Duration(milliseconds: 50));

    await tester.tap(find.widgetWithText(FilledButton, 'Tap to talk'));
    await tester.pump(const Duration(milliseconds: 50));

    expect(capture.started, isTrue);
    expect(find.widgetWithText(OutlinedButton, 'Stop'), findsOneWidget);
  });

  testWidgets('denied mic explains and offers text', (tester) async {
    await tester.pumpWidget(
      harness(micThrows: const AudioException('Permission denied')),
    );
    await tester.pump(const Duration(milliseconds: 50));

    await tester.tap(find.widgetWithText(FilledButton, 'Tap to talk'));
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.textContaining('Microphone access is blocked'), findsOneWidget);
    // Two "Type instead" buttons can appear (denied-help + the collapsed
    // affordance); tapping either should reveal the composer.
    await tester.tap(find.widgetWithText(TextButton, 'Type instead').first);
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.byType(TextField), findsOneWidget);
  });

  testWidgets('type instead reveals the text composer', (tester) async {
    await tester.pumpWidget(harness());
    await tester.pump(const Duration(milliseconds: 50));

    await tester.tap(find.widgetWithText(TextButton, 'Type instead'));
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.byType(TextField), findsOneWidget);
  });
}

/// Seeds a non-null access token so VoiceScreen._startVoice runs.
class _SeededToken extends AccessTokenNotifier {
  @override
  String? build() => 'test-token';
}
