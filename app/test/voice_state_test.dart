import 'package:edith_app/voice/voice_state.dart';
import 'package:edith_app/ws/events.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('shouldBargeIn', () {
    test('fires when EDITH is speaking and not yet debounced', () {
      expect(
        shouldBargeIn(
          sessionState: SessionState.speaking,
          alreadyBargedIn: false,
        ),
        isTrue,
      );
    });

    test('does not fire twice in one speaking turn', () {
      expect(
        shouldBargeIn(
          sessionState: SessionState.speaking,
          alreadyBargedIn: true,
        ),
        isFalse,
      );
    });

    test('does not fire when EDITH is not speaking', () {
      for (final s in [
        SessionState.idle,
        SessionState.listening,
        SessionState.thinking,
      ]) {
        expect(
          shouldBargeIn(sessionState: s, alreadyBargedIn: false),
          isFalse,
          reason: 'state $s should not barge in',
        );
      }
    });
  });

  group('VoiceState', () {
    test('isVoiceOn reflects mic state', () {
      expect(const VoiceState().isVoiceOn, isFalse);
      expect(
        const VoiceState(micState: MicState.capturing).isVoiceOn,
        isTrue,
      );
    });

    test('isSpeaking tracks the session state', () {
      expect(
        const VoiceState(sessionState: SessionState.speaking).isSpeaking,
        isTrue,
      );
      expect(const VoiceState().isSpeaking, isFalse);
    });

    test('copyWith clears the error when asked', () {
      const s = VoiceState(errorMessage: 'mic denied');
      expect(s.copyWith(clearError: true).errorMessage, isNull);
      expect(s.copyWith().errorMessage, 'mic denied');
    });
  });
}
