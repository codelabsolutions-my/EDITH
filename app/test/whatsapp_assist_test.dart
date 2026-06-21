import 'package:edith_app/whatsapp/whatsapp_assist.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const methodChannel = MethodChannel('edith/whatsapp');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  group('ChannelWhatsAppAssist (Android)', () {
    final calls = <MethodCall>[];

    setUp(() {
      calls.clear();
      messenger.setMockMethodCallHandler(methodChannel, (call) async {
        calls.add(call);
        switch (call.method) {
          case 'hasPermission':
            return true;
          case 'reply':
            return true;
          default:
            return null;
        }
      });
    });

    tearDown(() {
      messenger.setMockMethodCallHandler(methodChannel, null);
    });

    ChannelWhatsAppAssist build() =>
        ChannelWhatsAppAssist(supportedOverride: true);

    test('isSupported reflects the override', () {
      expect(build().isSupported, isTrue);
    });

    test('hasPermission round-trips the method channel', () async {
      expect(await build().hasPermission(), isTrue);
      expect(calls.single.method, 'hasPermission');
    });

    test('reply passes key + text and returns the native result', () async {
      final ok = await build().reply(notificationKey: 'k1', text: 'hello');
      expect(ok, isTrue);
      final call = calls.single;
      expect(call.method, 'reply');
      expect(call.arguments, {'key': 'k1', 'text': 'hello'});
    });

    test('openPermissionSettings invokes the channel', () async {
      await build().openPermissionSettings();
      expect(calls.single.method, 'openPermissionSettings');
    });

    test('reply surfaces a PlatformException as WhatsAppAssistException',
        () async {
      messenger.setMockMethodCallHandler(methodChannel, (call) async {
        throw PlatformException(code: 'err', message: 'no listener');
      });
      expect(
        () => build().reply(notificationKey: 'k', text: 't'),
        throwsA(isA<WhatsAppAssistException>()),
      );
    });
  });

  group('ChannelWhatsAppAssist (unsupported platform)', () {
    final assist = ChannelWhatsAppAssist(supportedOverride: false);

    test('isSupported is false and permission is denied', () async {
      expect(assist.isSupported, isFalse);
      expect(await assist.hasPermission(), isFalse);
    });

    test('incoming is an empty stream', () {
      expect(assist.incoming, emitsDone);
    });

    test('reply throws because it is Android-only', () {
      expect(
        () => assist.reply(notificationKey: 'k', text: 't'),
        throwsA(isA<WhatsAppAssistException>()),
      );
    });
  });

  group('UnsupportedWhatsAppAssist', () {
    const assist = UnsupportedWhatsAppAssist();

    test('is never supported', () async {
      expect(assist.isSupported, isFalse);
      expect(await assist.hasPermission(), isFalse);
      expect(assist.incoming, emitsDone);
    });
  });
}
