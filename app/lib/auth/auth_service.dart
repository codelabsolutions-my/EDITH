import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';
import 'auth_user.dart';
import 'token_store.dart';

/// Raised when an auth REST call returns a non-2xx response.
class AuthException implements Exception {
  const AuthException(this.statusCode, this.message);

  final int statusCode;
  final String message;

  @override
  String toString() => 'AuthException($statusCode): $message';
}

/// Talks to the server's REST auth contract and persists the tokens.
///
/// The [http.Client] and [TokenStore] are injected so tests can supply mocks.
class AuthService {
  AuthService({
    required this.tokenStore,
    http.Client? client,
    this.baseUrl = AppConfig.baseUrl,
  }) : _client = client ?? http.Client();

  final TokenStore tokenStore;
  final http.Client _client;
  final String baseUrl;

  /// `POST /auth/dev-login` — mints a session for a dev identity.
  Future<AuthSession> devLogin({
    required String email,
    required String displayName,
  }) async {
    final body = jsonEncode({
      'email': email,
      'display_name': displayName,
    });
    final json = await _post('/auth/dev-login', body);

    final session = AuthSession(
      accessToken: json['access_token'] as String,
      refreshToken: json['refresh_token'] as String,
      user: AuthUser.fromJson(json['user'] as Map<String, dynamic>),
    );
    await tokenStore.write(
      access: session.accessToken,
      refresh: session.refreshToken,
    );
    return session;
  }

  /// `POST /auth/google` — exchanges a verified Google `id_token` (from the
  /// native Google Sign-In SDK) for our session. Same token handling as
  /// [devLogin]: stores the pair in the secure store.
  Future<AuthSession> googleLogin({required String idToken}) async {
    final json = await _post(
      '/auth/google',
      jsonEncode({'id_token': idToken}),
    );
    final session = AuthSession(
      accessToken: json['access_token'] as String,
      refreshToken: json['refresh_token'] as String,
      user: AuthUser.fromJson(json['user'] as Map<String, dynamic>),
    );
    await tokenStore.write(
      access: session.accessToken,
      refresh: session.refreshToken,
    );
    return session;
  }

  /// `POST /auth/refresh` — swaps a refresh token for a fresh pair.
  ///
  /// Returns the new access token, having persisted both new tokens.
  Future<String> refresh() async {
    final refreshToken = await tokenStore.readRefresh();
    if (refreshToken == null) {
      throw const AuthException(401, 'no refresh token stored');
    }
    final json = await _post(
      '/auth/refresh',
      jsonEncode({'refresh_token': refreshToken}),
    );
    final access = json['access_token'] as String;
    final refresh = json['refresh_token'] as String;
    await tokenStore.write(access: access, refresh: refresh);
    return access;
  }

  /// `POST /auth/logout` — revokes the refresh token and clears local storage.
  Future<void> logout() async {
    final refreshToken = await tokenStore.readRefresh();
    if (refreshToken != null) {
      try {
        await _post('/auth/logout', jsonEncode({'refresh_token': refreshToken}));
      } on AuthException {
        // Best effort: clear locally even if the server rejects the call.
      }
    }
    await tokenStore.clear();
  }

  Future<Map<String, dynamic>> _post(String path, String body) async {
    final response = await _client.post(
      Uri.parse('$baseUrl$path'),
      headers: const {'content-type': 'application/json'},
      body: body,
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw AuthException(response.statusCode, response.body);
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  void close() => _client.close();
}
