import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers.dart';
import '../ws/events.dart';
import '../ws/ws_transport.dart';
import 'chat_models.dart';
import 'chat_reducer.dart';

/// Drives the chat: feeds inbound [WsTransport] events through [reduce], and
/// optimistically reflects the user's own sends.
///
/// The transport is normally resolved from [wsTransportProvider]; tests pass an
/// explicit [transportOverride] to inject a fake.
class ChatController extends Notifier<ChatState> {
  ChatController({WsTransport? transportOverride})
      // ignore: prefer_initializing_formals
      : _transportOverride = transportOverride;

  final WsTransport? _transportOverride;
  late final WsTransport _transport;
  StreamSubscription<InboundEvent>? _sub;

  @override
  ChatState build() {
    _transport = _transportOverride ?? ref.read(wsTransportProvider);
    _sub = _transport.events.listen(_onEvent);
    ref.onDispose(() => _sub?.cancel());
    return const ChatState();
  }

  void _onEvent(InboundEvent event) {
    state = reduce(state, event);
  }

  /// Open the connection and run the auth handshake.
  void connect(String accessToken) {
    _transport.connect(accessToken);
  }

  /// Send a user turn, echoing it locally and marking the session as thinking
  /// so the input disables immediately (the server also confirms via status).
  void sendText(String content) {
    final trimmed = content.trim();
    if (trimmed.isEmpty || !state.canSend) {
      return;
    }
    state = state.copyWith(
      messages: [
        ...state.messages,
        ChatMessage(role: MessageRole.user, text: trimmed),
      ],
      sessionState: SessionState.thinking,
      clearError: true,
    );
    _transport.sendText(trimmed);
  }

  /// Answer a pending confirm and clear it.
  void respondConfirm({required bool ok}) {
    final pending = state.pendingConfirm;
    if (pending == null) {
      return;
    }
    _transport.sendConfirm(actionId: pending.actionId, ok: ok);
    state = state.copyWith(
      clearPendingConfirm: true,
      sessionState: ok ? SessionState.thinking : SessionState.idle,
    );
  }

  /// Interrupt the current turn.
  void bargeIn() {
    _transport.sendBargeIn();
    state = state.copyWith(sessionState: SessionState.idle);
  }
}
