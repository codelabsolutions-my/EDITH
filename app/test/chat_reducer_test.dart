import 'package:edith_app/chat/chat_models.dart';
import 'package:edith_app/chat/chat_reducer.dart';
import 'package:edith_app/ws/events.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('reduce', () {
    test('auth_ok marks the session connected', () {
      final state = reduce(const ChatState(), const AuthOkEvent(user: {}));
      expect(state.connected, isTrue);
    });

    test('edith transcript chunks accumulate into one streaming message', () {
      var state = const ChatState();
      state = reduce(
        state,
        const TranscriptEvent(role: 'edith', text: 'Hello', isFinal: false),
      );
      state = reduce(
        state,
        const TranscriptEvent(role: 'edith', text: ' there', isFinal: false),
      );

      expect(state.messages, hasLength(1));
      expect(state.messages.single.text, 'Hello there');
      expect(state.messages.single.role, MessageRole.edith);
      expect(state.messages.single.isStreaming, isTrue);
    });

    test('turn_end finalizes the streaming edith message and idles', () {
      var state = reduce(
        const ChatState(sessionState: SessionState.thinking),
        const TranscriptEvent(role: 'edith', text: 'Done', isFinal: false),
      );
      state = reduce(state, const TurnEndEvent());

      expect(state.messages.single.isStreaming, isFalse);
      expect(state.sessionState, SessionState.idle);
      expect(state.activeTool, isNull);
    });

    test('a user transcript is its own non-streaming message', () {
      final state = reduce(
        const ChatState(),
        const TranscriptEvent(role: 'user', text: 'hi', isFinal: true),
      );
      expect(state.messages.single.role, MessageRole.user);
      expect(state.messages.single.isStreaming, isFalse);
    });

    test('a new edith turn after finalization starts a fresh message', () {
      var state = const ChatState();
      state = reduce(
        state,
        const TranscriptEvent(role: 'edith', text: 'one', isFinal: false),
      );
      state = reduce(state, const TurnEndEvent());
      state = reduce(
        state,
        const TranscriptEvent(role: 'edith', text: 'two', isFinal: false),
      );

      expect(state.messages, hasLength(2));
      expect(state.messages.last.text, 'two');
      expect(state.messages.last.isStreaming, isTrue);
    });

    test('confirm_request surfaces a pending confirm', () {
      final state = reduce(
        const ChatState(),
        const ConfirmRequestEvent(actionId: 'a1', summary: 'Send email?'),
      );
      expect(state.pendingConfirm, isNotNull);
      expect(state.pendingConfirm!.actionId, 'a1');
      expect(state.pendingConfirm!.summary, 'Send email?');
      expect(state.canSend, isFalse);
    });

    test('tool_event running then done toggles the active tool', () {
      var state = reduce(
        const ChatState(),
        const ToolEvent(name: 'calendar', toolState: ToolState.running),
      );
      expect(state.activeTool, 'calendar');

      state = reduce(
        state,
        const ToolEvent(name: 'calendar', toolState: ToolState.done),
      );
      expect(state.activeTool, isNull);
    });

    test('status updates the session state', () {
      final state = reduce(
        const ChatState(),
        const StatusEvent(sessionState: SessionState.thinking),
      );
      expect(state.sessionState, SessionState.thinking);
      expect(state.isBusy, isTrue);
    });

    test('error surfaces the message', () {
      final state = reduce(
        const ChatState(),
        const ErrorEvent(code: 'boom', message: 'kaput'),
      );
      expect(state.errorMessage, 'kaput');
    });
  });

  group('InboundEvent.fromJson', () {
    test('decodes known frames by type', () {
      expect(
        InboundEvent.fromJson({'type': 'turn_end'}),
        isA<TurnEndEvent>(),
      );
      expect(
        InboundEvent.fromJson({
          'type': 'transcript',
          'role': 'edith',
          'text': 'hi',
          'final': false,
        }),
        isA<TranscriptEvent>(),
      );
    });

    test('unknown type decodes to UnknownEvent', () {
      final event = InboundEvent.fromJson({'type': 'mystery'});
      expect(event, isA<UnknownEvent>());
      expect((event as UnknownEvent).type, 'mystery');
    });

    test('missing fields fall back to safe defaults', () {
      final event = InboundEvent.fromJson({'type': 'transcript'});
      expect(event, isA<TranscriptEvent>());
      final t = event as TranscriptEvent;
      expect(t.role, 'edith');
      expect(t.text, '');
      expect(t.isFinal, isFalse);
    });
  });
}
