import 'dart:convert';

import 'package:edith_app/chat/chat_controller.dart';
import 'package:edith_app/chat/chat_models.dart';
import 'package:edith_app/providers.dart';
import 'package:edith_app/ws/events.dart';
import 'package:edith_app/ws/ws_transport.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'ws_transport_test.dart' show FakeWebSocketChannel;

void main() {
  late FakeWebSocketChannel fake;
  late WsTransport transport;
  late ProviderContainer container;

  setUp(() {
    fake = FakeWebSocketChannel();
    transport = WsTransport(
      url: 'ws://test/ws',
      channelFactory: (_) => fake,
    );
    container = ProviderContainer(
      overrides: [
        wsTransportProvider.overrideWithValue(transport),
      ],
    );
  });

  tearDown(() {
    container.dispose();
    transport.dispose();
  });

  ChatController controller() =>
      container.read(chatControllerProvider.notifier);
  ChatState read() => container.read(chatControllerProvider);

  Future<void> settle() => Future<void>.delayed(Duration.zero);

  test('sendText is blocked until auth_ok connects the session', () async {
    controller().connect('tok');
    // Not yet connected -> canSend is false, send is ignored.
    controller().sendText('hi');
    expect(read().messages, isEmpty);

    fake.emit(jsonEncode({'type': 'auth_ok', 'user': {}}));
    await settle();
    expect(read().connected, isTrue);
  });

  test('sendText echoes the user message and marks thinking', () async {
    controller().connect('tok');
    fake.emit(jsonEncode({'type': 'auth_ok', 'user': {}}));
    await settle();
    fake.sentFrames.clear();

    controller().sendText('  book a meeting  ');

    final state = read();
    expect(state.messages.single.role, MessageRole.user);
    expect(state.messages.single.text, 'book a meeting');
    expect(state.sessionState, SessionState.thinking);
    expect(state.canSend, isFalse);

    final frame = jsonDecode(fake.sentFrames.single as String);
    expect(frame, {'type': 'text', 'content': 'book a meeting'});
  });

  test('respondConfirm clears the pending confirm and replies', () async {
    controller().connect('tok');
    fake.emit(jsonEncode({'type': 'auth_ok', 'user': {}}));
    fake.emit(jsonEncode({
      'type': 'confirm_request',
      'action_id': 'a9',
      'summary': 'Send WhatsApp?',
    }));
    await settle();
    expect(read().pendingConfirm, isNotNull);
    fake.sentFrames.clear();

    controller().respondConfirm(ok: true);
    await settle();

    expect(read().pendingConfirm, isNull);
    final frame = jsonDecode(fake.sentFrames.single as String);
    expect(frame, {'type': 'confirm', 'action_id': 'a9', 'ok': true});
  });

  test('a full streamed reply accumulates and finalizes', () async {
    controller().connect('tok');
    fake.emit(jsonEncode({'type': 'auth_ok', 'user': {}}));
    await settle();

    fake.emit(jsonEncode({'type': 'status', 'state': 'thinking'}));
    fake.emit(jsonEncode({
      'type': 'transcript',
      'role': 'edith',
      'text': 'Sure',
      'final': false,
    }));
    fake.emit(jsonEncode({
      'type': 'transcript',
      'role': 'edith',
      'text': ', done.',
      'final': false,
    }));
    fake.emit(jsonEncode({'type': 'turn_end'}));
    await settle();

    final state = read();
    expect(state.messages.single.text, 'Sure, done.');
    expect(state.messages.single.isStreaming, isFalse);
    expect(state.sessionState, SessionState.idle);
    expect(state.canSend, isTrue);
  });
}
