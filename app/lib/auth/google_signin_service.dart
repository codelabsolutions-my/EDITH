import 'package:google_sign_in/google_sign_in.dart';

import '../config.dart';

/// The outcome of a Google sign-in attempt.
class GoogleSignInResult {
  const GoogleSignInResult({required this.idToken, this.email, this.displayName});

  /// The Google-issued OIDC id_token to hand to the server.
  final String idToken;
  final String? email;
  final String? displayName;
}

/// Raised when Google sign-in fails or is cancelled.
class GoogleSignInFailure implements Exception {
  const GoogleSignInFailure(this.message);

  final String message;

  @override
  String toString() => 'GoogleSignInFailure: $message';
}

/// Thin wrapper over the `google_sign_in` plugin (v7 API).
///
/// Abstracted so the UI depends on [signIn] returning an id_token, and tests
/// can substitute a fake without the real plugin / platform channels.
abstract class GoogleSignInService {
  /// Trigger the interactive sign-in and return the id_token (+ profile).
  /// Throws [GoogleSignInFailure] on cancel/error.
  Future<GoogleSignInResult> signIn();

  /// Sign out of the Google session (does not revoke our server session).
  Future<void> signOut();
}

/// Default implementation backed by `GoogleSignIn.instance` (v7).
///
/// The server verifies the id_token's audience, so we pass our **web** client
/// ID as `serverClientId` on mobile — that makes Google mint an id_token whose
/// `aud` the server accepts (it lists the web + mobile client IDs in
/// `GOOGLE_ALLOWED_AUDIENCES`).
class PluginGoogleSignInService implements GoogleSignInService {
  PluginGoogleSignInService({GoogleSignIn? signIn})
      : _googleSignIn = signIn ?? GoogleSignIn.instance;

  final GoogleSignIn _googleSignIn;
  bool _initialized = false;

  Future<void> _ensureInitialized() async {
    if (_initialized) {
      return;
    }
    await _googleSignIn.initialize(
      // serverClientId: the web client ID, so the id_token audience matches the
      // server. clientId is only needed on web/iOS where the platform requires
      // its own client; passing the iOS id there is harmless elsewhere.
      serverClientId:
          AppConfig.googleWebClientId.isEmpty ? null : AppConfig.googleWebClientId,
      clientId:
          AppConfig.googleIosClientId.isEmpty ? null : AppConfig.googleIosClientId,
    );
    _initialized = true;
  }

  @override
  Future<GoogleSignInResult> signIn() async {
    await _ensureInitialized();
    if (!_googleSignIn.supportsAuthenticate()) {
      // Web uses a button-based flow, not authenticate(); handled separately in
      // the UI on that platform.
      throw const GoogleSignInFailure(
        'interactive authenticate() is unavailable on this platform',
      );
    }
    final GoogleSignInAccount account;
    try {
      account = await _googleSignIn.authenticate(scopeHint: const ['email']);
    } on GoogleSignInException catch (e) {
      throw GoogleSignInFailure(e.code == GoogleSignInExceptionCode.canceled
          ? 'sign-in cancelled'
          : 'sign-in failed: ${e.description ?? e.code.name}');
    }
    final idToken = account.authentication.idToken;
    if (idToken == null) {
      throw const GoogleSignInFailure('no id_token returned by Google');
    }
    return GoogleSignInResult(
      idToken: idToken,
      email: account.email,
      displayName: account.displayName,
    );
  }

  @override
  Future<void> signOut() => _googleSignIn.signOut();
}
