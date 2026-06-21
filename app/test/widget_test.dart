import 'package:edith_app/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('app boots to the login screen with Google sign-in', (
    tester,
  ) async {
    await tester.pumpWidget(const ProviderScope(child: EdithApp()));
    await tester.pumpAndSettle();

    expect(find.text('Sign in to EDITH'), findsOneWidget);
    expect(find.text('Sign in with Google'), findsOneWidget);
    // Dev login is hidden behind a toggle by default.
    expect(find.byType(TextField), findsNothing);
  });

  testWidgets('dev login form expands on toggle', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: EdithApp()));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Dev login (local testing)'));
    await tester.pumpAndSettle();

    expect(find.byType(TextField), findsNWidgets(2));
    expect(find.text('Dev sign in'), findsOneWidget);
  });
}
