import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Persists the access/refresh tokens in the platform secure store.
///
/// Abstracted behind an interface so tests can inject an in-memory fake
/// instead of touching the real keychain.
abstract class TokenStore {
  Future<void> write({required String access, required String refresh});
  Future<String?> readAccess();
  Future<String?> readRefresh();
  Future<void> clear();
}

/// Default [TokenStore] backed by `flutter_secure_storage`.
class SecureTokenStore implements TokenStore {
  SecureTokenStore([FlutterSecureStorage? storage])
      : _storage = storage ?? const FlutterSecureStorage();

  static const _accessKey = 'edith.access_token';
  static const _refreshKey = 'edith.refresh_token';

  final FlutterSecureStorage _storage;

  @override
  Future<void> write({required String access, required String refresh}) async {
    await _storage.write(key: _accessKey, value: access);
    await _storage.write(key: _refreshKey, value: refresh);
  }

  @override
  Future<String?> readAccess() => _storage.read(key: _accessKey);

  @override
  Future<String?> readRefresh() => _storage.read(key: _refreshKey);

  @override
  Future<void> clear() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}

/// In-memory [TokenStore] for tests and ephemeral sessions.
class InMemoryTokenStore implements TokenStore {
  String? _access;
  String? _refresh;

  @override
  Future<void> write({required String access, required String refresh}) async {
    _access = access;
    _refresh = refresh;
  }

  @override
  Future<String?> readAccess() async => _access;

  @override
  Future<String?> readRefresh() async => _refresh;

  @override
  Future<void> clear() async {
    _access = null;
    _refresh = null;
  }
}
