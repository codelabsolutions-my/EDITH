import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'ui/login_screen.dart';

void main() {
  runApp(const ProviderScope(child: EdithApp()));
}

class EdithApp extends StatelessWidget {
  const EdithApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'EDITH',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF6C5CE7)),
        useMaterial3: true,
      ),
      home: const LoginScreen(),
    );
  }
}
