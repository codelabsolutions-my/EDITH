/// An incoming WhatsApp message captured from an Android notification.
///
/// Sourced from the NotificationListenerService (official OS API) — never from
/// scraping WhatsApp Web. iOS cannot provide this.
class WhatsAppMessage {
  const WhatsAppMessage({
    required this.sender,
    required this.text,
    required this.notificationKey,
    required this.canReply,
    this.timestamp,
  });

  /// Best-effort decode of the platform-channel map sent by the native service.
  factory WhatsAppMessage.fromMap(Map<dynamic, dynamic> map) {
    final millis = map['timestamp'];
    return WhatsAppMessage(
      sender: (map['sender'] as String?) ?? '',
      text: (map['text'] as String?) ?? '',
      notificationKey: (map['key'] as String?) ?? '',
      // Whether the notification carried a RemoteInput direct-reply action.
      canReply: (map['canReply'] as bool?) ?? false,
      timestamp: millis is int
          ? DateTime.fromMillisecondsSinceEpoch(millis)
          : null,
    );
  }

  /// Display name of the chat/sender as WhatsApp labelled the notification.
  final String sender;

  /// The message body.
  final String text;

  /// Opaque key identifying the originating notification; passed back to the
  /// native side to target the correct RemoteInput when replying.
  final String notificationKey;

  /// True when the notification exposed a direct-reply action we can use.
  final bool canReply;

  final DateTime? timestamp;
}
