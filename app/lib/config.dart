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
}
