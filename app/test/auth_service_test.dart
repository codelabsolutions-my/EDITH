import 'dart:convert';

import 'package:edith_app/auth/auth_service.dart';
import 'package:edith_app/auth/token_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  group('AuthService.devLogin', () {
    test('posts credentials and persists the returned tokens', () async {
      late http.Request captured;
      final client = MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode({
            'access_token': 'acc',
            'refresh_token': 'ref',
            'user': {
              'id': 'u1',
              'display_name': 'Ayu',
              'primary_email': 'ayu@example.my',
            },
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final store = InMemoryTokenStore();
      final service = AuthService(
        tokenStore: store,
        client: client,
        baseUrl: 'http://server',
      );

      final session = await service.devLogin(
        email: 'ayu@example.my',
        displayName: 'Ayu',
      );

      expect(captured.url.toString(), 'http://server/auth/dev-login');
      expect(jsonDecode(captured.body), {
        'email': 'ayu@example.my',
        'display_name': 'Ayu',
      });
      expect(session.accessToken, 'acc');
      expect(session.user.displayName, 'Ayu');
      expect(await store.readAccess(), 'acc');
      expect(await store.readRefresh(), 'ref');
    });

    test('throws AuthException on a non-2xx response', () async {
      final client = MockClient((_) async => http.Response('nope', 401));
      final service = AuthService(
        tokenStore: InMemoryTokenStore(),
        client: client,
        baseUrl: 'http://server',
      );

      expect(
        () => service.devLogin(email: 'x@y.z', displayName: 'X'),
        throwsA(isA<AuthException>()),
      );
    });
  });

  group('AuthService.googleLogin', () {
    test('posts the id_token and persists the returned session', () async {
      late http.Request captured;
      final client = MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode({
            'access_token': 'gacc',
            'refresh_token': 'gref',
            'user': {
              'id': 'g1',
              'display_name': 'Siti',
              'primary_email': 'siti@gmail.com',
            },
          }),
          200,
        );
      });
      final store = InMemoryTokenStore();
      final service = AuthService(
        tokenStore: store,
        client: client,
        baseUrl: 'http://server',
      );

      final session = await service.googleLogin(idToken: 'google-id-token');

      expect(captured.url.toString(), 'http://server/auth/google');
      expect(jsonDecode(captured.body), {'id_token': 'google-id-token'});
      expect(session.accessToken, 'gacc');
      expect(session.user.primaryEmail, 'siti@gmail.com');
      expect(await store.readAccess(), 'gacc');
      expect(await store.readRefresh(), 'gref');
    });

    test('throws AuthException when the server rejects the id_token', () async {
      final client = MockClient((_) async => http.Response('bad token', 401));
      final service = AuthService(
        tokenStore: InMemoryTokenStore(),
        client: client,
        baseUrl: 'http://server',
      );
      expect(
        () => service.googleLogin(idToken: 'nope'),
        throwsA(isA<AuthException>()),
      );
    });
  });

  group('AuthService.refresh', () {
    test('swaps the stored refresh token for a fresh pair', () async {
      final store = InMemoryTokenStore();
      await store.write(access: 'old-acc', refresh: 'old-ref');
      late http.Request captured;
      final client = MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode({'access_token': 'new-acc', 'refresh_token': 'new-ref'}),
          200,
        );
      });
      final service = AuthService(
        tokenStore: store,
        client: client,
        baseUrl: 'http://server',
      );

      final access = await service.refresh();

      expect(jsonDecode(captured.body), {'refresh_token': 'old-ref'});
      expect(access, 'new-acc');
      expect(await store.readRefresh(), 'new-ref');
    });

    test('throws when no refresh token is stored', () async {
      final service = AuthService(
        tokenStore: InMemoryTokenStore(),
        client: MockClient((_) async => http.Response('{}', 200)),
        baseUrl: 'http://server',
      );
      expect(service.refresh, throwsA(isA<AuthException>()));
    });
  });

  group('AuthService.logout', () {
    test('clears local tokens even when the server rejects', () async {
      final store = InMemoryTokenStore();
      await store.write(access: 'a', refresh: 'r');
      final service = AuthService(
        tokenStore: store,
        client: MockClient((_) async => http.Response('err', 500)),
        baseUrl: 'http://server',
      );

      await service.logout();

      expect(await store.readAccess(), isNull);
      expect(await store.readRefresh(), isNull);
    });
  });
}
