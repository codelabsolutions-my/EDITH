import 'package:flutter/foundation.dart';
import 'package:home_widget/home_widget.dart';

/// Bridges the Flutter app to the Android home-screen widget via `home_widget`.
///
/// The widget shows a short status line and, when tapped, launches the app with
/// a deep-link URI that [HomeWidgetLaunch] interprets to jump straight into a
/// voice session.
class HomeWidgetService {
  const HomeWidgetService();

  /// The Android widget provider class name (matches the native
  /// AppWidgetProvider registered in AndroidManifest.xml).
  static const String _androidWidgetName = 'EdithWidgetProvider';

  /// Keys written to the widget's shared prefs and read by the native layout.
  static const String statusKey = 'edith_status';

  /// Host of the deep-link URI the widget fires on tap.
  static const String voiceLaunchHost = 'voice';

  bool get _supported => !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  /// Push a status string to the widget (e.g. "Tap to talk", "Listening…").
  Future<void> setStatus(String status) async {
    if (!_supported) {
      return;
    }
    try {
      await HomeWidget.saveWidgetData<String>(statusKey, status);
      await HomeWidget.updateWidget(androidName: _androidWidgetName);
    } catch (_) {
      // No widget plugin/host (e.g. tests, or widget never added) — ignore.
    }
  }

  /// The URI used by the widget's tap action; the app deep-links on it.
  static Uri get voiceLaunchUri => Uri(scheme: 'edith', host: voiceLaunchHost);

  /// Whether a launch URI means "open in voice mode".
  static bool isVoiceLaunch(Uri? uri) =>
      uri != null && uri.scheme == 'edith' && uri.host == voiceLaunchHost;
}
