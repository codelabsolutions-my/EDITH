import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../config.dart';
import 'events.dart';

/// Builds a [WebSocketChannel] for a given URL.
///
/// Injected so tests can hand the transport a fake channel without a real
/// socket.
typedef ChannelFactory = WebSocketChannel Function(Uri url);

WebSocketChannel _defaultChannelFactory(Uri url) =>
    WebSocketChannel.connect(url);

/// Owns the `/ws` connection: performs the auth handshake, decodes inbound
/// frames into [InboundEvent]s, and exposes typed send methods.
class WsTransport {
  WsTransport({
    this.url = AppConfig.wsUrl,
    this.channelFactory = _defaultChannelFactory,
  });

  final String url;
  final ChannelFactory channelFactory;

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _sub;
  final _events = StreamController<InboundEvent>.broadcast();

  /// Typed stream of every server -> client frame.
  Stream<InboundEvent> get events => _events.stream;

  bool get isConnected => _channel != null;

  /// Connect and send the auth frame.
  ///
  /// Does not wait for `auth_ok`; callers observe [events] for the handshake
  /// result so the connection state stays in one place.
  void connect(String accessToken) {
    if (_channel != null) {
      return;
    }
    final channel = channelFactory(Uri.parse(url));
    _channel = channel;
    _sub = channel.stream.listen(
      _onData,
      onError: _onError,
      onDone: _onDone,
    );
    send({'type': 'auth', 'token': accessToken});
  }

  void _onData(dynamic data) {
    if (data is! String) {
      return;
    }
    final Map<String, dynamic> json;
    try {
      final decoded = jsonDecode(data);
      if (decoded is! Map<String, dynamic>) {
        return;
      }
      json = decoded;
    } on FormatException {
      return;
    }
    _events.add(InboundEvent.fromJson(json));
  }

  void _onError(Object error) {
    _events.add(ErrorEvent(code: 'ws_error', message: error.toString()));
  }

  void _onDone() {
    final code = _channel?.closeCode;
    _channel = null;
    _events.add(ErrorEvent(
      code: 'ws_closed',
      message: 'connection closed${code != null ? ' ($code)' : ''}',
    ));
  }

  /// Send a user text turn.
  void sendText(String content) =>
      send({'type': 'text', 'content': content});

  /// Reply to a [ConfirmRequestEvent].
  void sendConfirm({required String actionId, required bool ok}) =>
      send({'type': 'confirm', 'action_id': actionId, 'ok': ok});

  /// Interrupt the current turn.
  void sendBargeIn() => send({'type': 'barge_in'});

  /// Encode and write a raw frame.
  void send(Map<String, dynamic> frame) {
    final channel = _channel;
    if (channel == null) {
      return;
    }
    channel.sink.add(jsonEncode(frame));
  }

  Future<void> dispose() async {
    await _sub?.cancel();
    await _channel?.sink.close();
    _channel = null;
    await _events.close();
  }
}
