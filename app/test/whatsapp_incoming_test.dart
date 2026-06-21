import 'package:edith_app/whatsapp/whatsapp_assist.dart';
import 'package:edith_app/whatsapp/whatsapp_message.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const eventChannelName = 'edith/whatsapp/incoming';
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  test('incoming decodes EventChannel payloads into WhatsAppMessage', () async {
    // Respond to the EventChannel's listen handshake, then push one event.
    messenger.setMockMethodCallHandler(
      const MethodChannel(eventChannelName),
      (call) async {
        if (call.method == 'listen') {
          // Deliver an incoming-message event on the channel.
          await messenger.handlePlatformMessage(
            eventChannelName,
            const StandardMethodCodec().encodeSuccessEnvelope({
              'sender': 'Mak',
              'text': 'Balik makan?',
              'key': 'k9',
              'canReply': true,
              'timestamp': 1700000000000,
            }),
            (_) {},
          );
        }
        return null;
      },
    );
    addTearDown(() => messenger.setMockMethodCallHandler(
          const MethodChannel(eventChannelName),
          null,
        ));

    final assist = ChannelWhatsAppAssist(supportedOverride: true);
    final msg = await assist.incoming.first;

    expect(msg, isA<WhatsAppMessage>());
    expect(msg.sender, 'Mak');
    expect(msg.text, 'Balik makan?');
    expect(msg.canReply, isTrue);
  });
}
