/// Server connection configuration.
///
/// Override at build/run time with `--dart-define`, e.g.
/// `flutter run --dart-define=EDITH_BASE_URL=http://10.0.2.2:8000`.
class AppConfig {
  const AppConfig._();

  /// REST base URL for the auth endpoints (no trailing slash).
  static const String baseUrl = String.fromEnvironment(
    'EDITH_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  /// WebSocket URL for the `/ws` session channel.
  static const String wsUrl = String.fromEnvironment(
    'EDITH_WS_URL',
    defaultValue: 'ws://localhost:8000/ws',
  );

  /// Google OAuth **web** client ID — required for Google Sign-In on the web
  /// target and used as the `serverClientId` on mobile so the issued id_token
  /// carries an audience the server accepts. The user creates this in Google
  /// Cloud Console; pass it via
  /// `--dart-define=GOOGLE_WEB_CLIENT_ID=xxxx.apps.googleusercontent.com`.
  static const String googleWebClientId = String.fromEnvironment(
    'GOOGLE_WEB_CLIENT_ID',
  );

  /// Google OAuth **iOS** client ID (only needed for the iOS build). Passed via
  /// `--dart-define=GOOGLE_IOS_CLIENT_ID=...`. Android derives its client from
  /// the SHA-1 + package registered in the console (no value needed here).
  static const String googleIosClientId = String.fromEnvironment(
    'GOOGLE_IOS_CLIENT_ID',
  );

  /// Whether a Google web client ID is configured (gates the Sign-in button on
  /// platforms that require it).
  static bool get hasGoogleWebClientId => googleWebClientId.isNotEmpty;
}
