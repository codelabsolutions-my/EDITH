import 'package:edith_app/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('app boots to the dev-login screen', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: EdithApp()));
    await tester.pumpAndSettle();

    expect(find.text('EDITH — Dev Login'), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget);
    expect(find.byType(TextField), findsNWidgets(2));
  });
}
