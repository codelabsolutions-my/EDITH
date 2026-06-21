import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:home_widget/home_widget.dart';

import 'providers.dart';
import 'ui/login_screen.dart';
import 'widget/home_widget_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final container = ProviderContainer();
  await _initHomeWidget(container);
  runApp(
    UncontrolledProviderScope(
      container: container,
      child: const EdithApp(),
    ),
  );
}

/// Detect whether the app was launched by tapping the home-screen widget
/// (Android only) and record it so the UI can jump into voice mode.
Future<void> _initHomeWidget(ProviderContainer container) async {
  if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) {
    return;
  }
  try {
    final launchUri = await HomeWidget.initiallyLaunchedFromHomeWidget();
    if (HomeWidgetService.isVoiceLaunch(launchUri)) {
      container.read(launchedForVoiceProvider.notifier).set(true);
    }
    HomeWidget.widgetClicked.listen((uri) {
      if (HomeWidgetService.isVoiceLaunch(uri)) {
        container.read(launchedForVoiceProvider.notifier).set(true);
      }
    });
  } catch (_) {
    // home_widget unavailable (e.g. no widget configured) — ignore.
  }
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
