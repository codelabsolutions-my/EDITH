import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'auth/auth_service.dart';
import 'auth/auth_user.dart';
import 'auth/token_store.dart';
import 'chat/chat_controller.dart';
import 'chat/chat_models.dart';
import 'ws/ws_transport.dart';

/// Secure token store, shared by the auth service and (later) reconnect logic.
final tokenStoreProvider = Provider<TokenStore>((ref) => SecureTokenStore());

/// REST auth client.
final authServiceProvider = Provider<AuthService>((ref) {
  final service = AuthService(tokenStore: ref.watch(tokenStoreProvider));
  ref.onDispose(service.close);
  return service;
});

/// Holds the currently authenticated user (null until dev-login succeeds).
class AuthUserNotifier extends Notifier<AuthUser?> {
  @override
  AuthUser? build() => null;

  void set(AuthUser? user) => state = user;
}

final authUserProvider =
    NotifierProvider<AuthUserNotifier, AuthUser?>(AuthUserNotifier.new);

/// The `/ws` transport, disposed with the provider scope.
final wsTransportProvider = Provider<WsTransport>((ref) {
  final transport = WsTransport();
  ref.onDispose(transport.dispose);
  return transport;
});

/// Conversation state + controls. The controller resolves the transport from
/// [wsTransportProvider] inside its `build`.
final chatControllerProvider =
    NotifierProvider<ChatController, ChatState>(ChatController.new);
