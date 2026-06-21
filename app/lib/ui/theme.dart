import 'package:flutter/material.dart';

/// EDITH's dark, holographic-HUD theme. The accent matches the orb (violet core
/// with a cyan secondary), on near-black surfaces for the AI-console feel.
class EdithTheme {
  const EdithTheme._();

  static const Color _violet = Color(0xFF8B7BFF);
  static const Color _cyan = Color(0xFF45E0D0);
  static const Color _bg = Color(0xFF0A0E17);
  static const Color _surface = Color(0xFF141A28);

  static ThemeData get dark {
    final scheme = ColorScheme.fromSeed(
      seedColor: _violet,
      brightness: Brightness.dark,
    ).copyWith(
      primary: _violet,
      secondary: _cyan,
      tertiary: _cyan,
      surface: _bg,
      surfaceContainerHighest: _surface,
    );

    final base = ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: scheme,
      scaffoldBackgroundColor: _bg,
    );

    return base.copyWith(
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: false,
      ),
      textTheme: base.textTheme.apply(
        bodyColor: const Color(0xFFE6EAF2),
        displayColor: Colors.white,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          shape: const StadiumBorder(),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: _surface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: _violet.withValues(alpha: 0.25)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: _cyan, width: 1.5),
        ),
      ),
    );
  }
}
