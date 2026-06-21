import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'whatsapp_message.dart';

/// Personal WhatsApp assist: read incoming messages and send direct replies via
/// Android's NotificationListenerService + the notification's RemoteInput.
///
/// This is an **Android-only, on-device** capability per the locked
/// architecture — official OS APIs, no server session, never WhatsApp Web
/// scraping, and impossible on iOS. The app and tests depend only on this
/// interface; the native bits sit behind it.
abstract class WhatsAppAssist {
  /// Whether this platform can ever support assist (Android only).
  bool get isSupported;

  /// Whether the user has granted notification-listener access. On unsupported
  /// platforms this is always false.
  Future<bool> hasPermission();

  /// Open the system notification-access settings so the user can grant the
  /// listener. No-op where unsupported.
  Future<void> openPermissionSettings();

  /// Stream of incoming WhatsApp messages observed by the listener service.
  Stream<WhatsAppMessage> get incoming;

  /// Send [text] as a direct reply to the notification identified by
  /// [notificationKey]. Returns true if the native side dispatched the
  /// RemoteInput. Throws [WhatsAppAssistException] on failure.
  Future<bool> reply({required String notificationKey, required String text});
}

/// Raised when a native assist operation fails.
class WhatsAppAssistException implements Exception {
  const WhatsAppAssistException(this.message);

  final String message;

  @override
  String toString() => 'WhatsAppAssistException: $message';
}

/// [WhatsAppAssist] backed by platform channels to the native
/// NotificationListenerService.
///
/// Channel names are shared with the Kotlin side:
///   * method channel `edith/whatsapp` — permission + reply RPCs
///   * event channel  `edith/whatsapp/incoming` — message stream
class ChannelWhatsAppAssist implements WhatsAppAssist {
  ChannelWhatsAppAssist({
    MethodChannel? methodChannel,
    EventChannel? eventChannel,
    bool? supportedOverride,
  })  : _method = methodChannel ?? const MethodChannel(_methodChannelName),
        _event = eventChannel ?? const EventChannel(_eventChannelName),
        _supported = supportedOverride ??
            (!kIsWeb && defaultTargetPlatform == TargetPlatform.android);

  static const String _methodChannelName = 'edith/whatsapp';
  static const String _eventChannelName = 'edith/whatsapp/incoming';

  final MethodChannel _method;
  final EventChannel _event;
  final bool _supported;

  Stream<WhatsAppMessage>? _incoming;

  @override
  bool get isSupported => _supported;

  @override
  Future<bool> hasPermission() async {
    if (!_supported) {
      return false;
    }
    final granted = await _method.invokeMethod<bool>('hasPermission');
    return granted ?? false;
  }

  @override
  Future<void> openPermissionSettings() async {
    if (!_supported) {
      return;
    }
    await _method.invokeMethod<void>('openPermissionSettings');
  }

  @override
  Stream<WhatsAppMessage> get incoming {
    if (!_supported) {
      return const Stream<WhatsAppMessage>.empty();
    }
    return _incoming ??= _event
        .receiveBroadcastStream()
        .map((event) => WhatsAppMessage.fromMap(event as Map<dynamic, dynamic>));
  }

  @override
  Future<bool> reply({
    required String notificationKey,
    required String text,
  }) async {
    if (!_supported) {
      throw const WhatsAppAssistException('WhatsApp assist is Android-only');
    }
    try {
      final ok = await _method.invokeMethod<bool>('reply', {
        'key': notificationKey,
        'text': text,
      });
      return ok ?? false;
    } on PlatformException catch (e) {
      throw WhatsAppAssistException(e.message ?? 'reply failed');
    }
  }
}

/// No-op assist for non-Android platforms (web/iOS/desktop).
class UnsupportedWhatsAppAssist implements WhatsAppAssist {
  const UnsupportedWhatsAppAssist();

  @override
  bool get isSupported => false;

  @override
  Future<bool> hasPermission() async => false;

  @override
  Future<void> openPermissionSettings() async {}

  @override
  Stream<WhatsAppMessage> get incoming => const Stream<WhatsAppMessage>.empty();

  @override
  Future<bool> reply({
    required String notificationKey,
    required String text,
  }) async {
    throw const WhatsAppAssistException('WhatsApp assist is Android-only');
  }
}
