import 'package:edith_app/widget/home_widget_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('HomeWidgetService.isVoiceLaunch', () {
    test('accepts the edith://voice deep link', () {
      expect(
        HomeWidgetService.isVoiceLaunch(Uri.parse('edith://voice')),
        isTrue,
      );
    });

    test('rejects a null or unrelated URI', () {
      expect(HomeWidgetService.isVoiceLaunch(null), isFalse);
      expect(
        HomeWidgetService.isVoiceLaunch(Uri.parse('https://example.com')),
        isFalse,
      );
      expect(
        HomeWidgetService.isVoiceLaunch(Uri.parse('edith://settings')),
        isFalse,
      );
    });

    test('voiceLaunchUri is the canonical deep link', () {
      expect(HomeWidgetService.voiceLaunchUri.toString(), 'edith://voice');
      expect(
        HomeWidgetService.isVoiceLaunch(HomeWidgetService.voiceLaunchUri),
        isTrue,
      );
    });
  });
}
