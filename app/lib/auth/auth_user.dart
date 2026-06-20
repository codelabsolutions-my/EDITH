/// The authenticated user as returned by the auth endpoints and `auth_ok`.
class AuthUser {
  const AuthUser({
    required this.id,
    required this.displayName,
    required this.primaryEmail,
  });

  factory AuthUser.fromJson(Map<String, dynamic> json) {
    return AuthUser(
      id: (json['id'] as String?) ?? '',
      displayName: (json['display_name'] as String?) ?? '',
      primaryEmail: (json['primary_email'] as String?) ?? '',
    );
  }

  final String id;
  final String displayName;
  final String primaryEmail;
}

/// A pair of session tokens plus the user they belong to.
class AuthSession {
  const AuthSession({
    required this.accessToken,
    required this.refreshToken,
    required this.user,
  });

  final String accessToken;
  final String refreshToken;
  final AuthUser user;
}
