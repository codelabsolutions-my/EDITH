import 'dart:convert';

import 'package:edith_app/auth/google_signin_service.dart';
import 'package:edith_app/auth/auth_service.dart';
import 'package:edith_app/auth/token_store.dart';
import 'package:edith_app/providers.dart';
import 'package:edith_app/ui/login_screen.dart';
import 'package:edith_app/ws/ws_transport.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'ws_transport_test.dart' show FakeWebSocketChannel;

/// Fake Google sign-in that returns a canned id_token (or throws).
class FakeGoogleSignInService implements GoogleSignInService {
  FakeGoogleSignInService({this.result, this.failure});

  final GoogleSignInResult? result;
  final GoogleSignInFailure? failure;
  bool signedOut = false;

  @override
  Future<GoogleSignInResult> signIn() async {
    if (failure != null) {
      throw failure!;
    }
    return result!;
  }

  @override
  Future<void> signOut() async {
    signedOut = true;
  }
}

void main() {
  testWidgets(
    'Google sign-in posts the id_token and navigates into the chat',
    (tester) async {
      late http.Request captured;
      final client = MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode({
            'access_token': 'acc',
            'refresh_token': 'ref',
            'user': {
              'id': 'u1',
              'display_name': 'Aiman',
              'primary_email': 'aiman@gmail.com',
            },
          }),
          200,
        );
      });
      final authService = AuthService(
        tokenStore: InMemoryTokenStore(),
        client: client,
        baseUrl: 'http://server',
      );
      final fakeGoogle = FakeGoogleSignInService(
        result: const GoogleSignInResult(idToken: 'id-tok', email: 'a@b.c'),
      );

      // A fake transport so navigating into the chat doesn't open a real socket.
      final transport = WsTransport(channelFactory: (_) => FakeWebSocketChannel());

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authServiceProvider.overrideWithValue(authService),
            googleSignInServiceProvider.overrideWithValue(fakeGoogle),
            wsTransportProvider.overrideWithValue(transport),
          ],
          child: const MaterialApp(home: LoginScreen()),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Sign in with Google'));
      await tester.pumpAndSettle();

      expect(captured.url.toString(), 'http://server/auth/google');
      expect(jsonDecode(captured.body), {'id_token': 'id-tok'});
      // Navigated away from the login screen.
      expect(find.text('Sign in with Google'), findsNothing);
    },
  );

  testWidgets('a cancelled Google sign-in shows the error and stays put', (
    tester,
  ) async {
    final authService = AuthService(
      tokenStore: InMemoryTokenStore(),
      client: MockClient((_) async => http.Response('{}', 200)),
      baseUrl: 'http://server',
    );
    final fakeGoogle = FakeGoogleSignInService(
      failure: const GoogleSignInFailure('sign-in cancelled'),
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authServiceProvider.overrideWithValue(authService),
          googleSignInServiceProvider.overrideWithValue(fakeGoogle),
        ],
        child: const MaterialApp(home: LoginScreen()),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Sign in with Google'));
    await tester.pumpAndSettle();

    expect(find.text('sign-in cancelled'), findsOneWidget);
    expect(find.text('Sign in with Google'), findsOneWidget);
  });
}
