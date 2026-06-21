import 'package:edith_app/whatsapp/whatsapp_message.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('WhatsAppMessage.fromMap', () {
    test('decodes a full notification map', () {
      final msg = WhatsAppMessage.fromMap({
        'sender': 'Ali',
        'text': 'Jom lunch?',
        'key': '0|com.whatsapp|123',
        'canReply': true,
        'timestamp': 1700000000000,
      });
      expect(msg.sender, 'Ali');
      expect(msg.text, 'Jom lunch?');
      expect(msg.notificationKey, '0|com.whatsapp|123');
      expect(msg.canReply, isTrue);
      expect(msg.timestamp, DateTime.fromMillisecondsSinceEpoch(1700000000000));
    });

    test('falls back to safe defaults for missing fields', () {
      final msg = WhatsAppMessage.fromMap({'text': 'hi'});
      expect(msg.sender, '');
      expect(msg.text, 'hi');
      expect(msg.notificationKey, '');
      expect(msg.canReply, isFalse);
      expect(msg.timestamp, isNull);
    });

    test('ignores a non-int timestamp', () {
      final msg = WhatsAppMessage.fromMap({'text': 'x', 'timestamp': 'nope'});
      expect(msg.timestamp, isNull);
    });
  });
}
