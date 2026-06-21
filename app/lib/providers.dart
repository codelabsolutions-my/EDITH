import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'auth/auth_service.dart';
import 'auth/auth_user.dart';
import 'auth/google_signin_service.dart';
import 'auth/token_store.dart';
import 'chat/chat_controller.dart';
import 'chat/chat_models.dart';
import 'voice/voice_controller.dart';
import 'voice/voice_state.dart';
import 'widget/home_widget_service.dart';
import 'ws/ws_transport.dart';

/// Secure token store, shared by the auth service and (later) reconnect logic.
final tokenStoreProvider = Provider<TokenStore>((ref) => SecureTokenStore());

/// REST auth client.
final authServiceProvider = Provider<AuthService>((ref) {
  final service = AuthService(tokenStore: ref.watch(tokenStoreProvider));
  ref.onDispose(service.close);
  return service;
});

/// Google Sign-In wrapper (overridden with a fake in tests).
final googleSignInServiceProvider =
    Provider<GoogleSignInService>((ref) => PluginGoogleSignInService());

/// Holds the currently authenticated user (null until dev-login succeeds).
class AuthUserNotifier extends Notifier<AuthUser?> {
  @override
  AuthUser? build() => null;

  void set(AuthUser? user) => state = user;
}

final authUserProvider =
    NotifierProvider<AuthUserNotifier, AuthUser?>(AuthUserNotifier.new);

/// The current access token, held in memory so the chat screen can reconnect
/// the WS in a different mode (text <-> voice) without re-reading storage.
class AccessTokenNotifier extends Notifier<String?> {
  @override
  String? build() => null;

  void set(String? token) => state = token;
}

final accessTokenProvider =
    NotifierProvider<AccessTokenNotifier, String?>(AccessTokenNotifier.new);

/// True when the app was launched by tapping the home-screen widget's
/// tap-to-talk action; the chat screen consumes it to auto-enable voice mode.
class LaunchedForVoiceNotifier extends Notifier<bool> {
  @override
  bool build() => false;

  void set(bool value) => state = value;
}

final launchedForVoiceProvider =
    NotifierProvider<LaunchedForVoiceNotifier, bool>(
        LaunchedForVoiceNotifier.new);

/// Android home-screen widget bridge (status push + tap deep-link).
final homeWidgetServiceProvider =
    Provider<HomeWidgetService>((ref) => const HomeWidgetService());

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

/// Voice subsystem: mic capture, PCM playback, barge-in, orb level.
final voiceControllerProvider =
    NotifierProvider<VoiceController, VoiceState>(VoiceController.new);
