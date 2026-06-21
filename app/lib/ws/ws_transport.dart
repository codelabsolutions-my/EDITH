import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

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
  final _audioFrames = StreamController<Uint8List>.broadcast();

  /// Typed stream of every server -> client JSON frame.
  Stream<InboundEvent> get events => _events.stream;

  /// Inbound binary audio frames (24 kHz mono 16-bit PCM from the server).
  ///
  /// Routed separately from [events] so the playback layer subscribes to raw
  /// PCM while the chat layer consumes JSON events.
  Stream<Uint8List> get audioFrames => _audioFrames.stream;

  bool get isConnected => _channel != null;

  /// Connect and send the auth frame.
  ///
  /// [mode] is `"text"` (default) or `"voice"`; the latter tells the server to
  /// open the audio pipeline. Does not wait for `auth_ok`; callers observe
  /// [events] for the handshake result so the connection state stays in one
  /// place.
  void connect(String accessToken, {String mode = 'text'}) {
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
    send({'type': 'auth', 'token': accessToken, 'mode': mode});
  }

  /// Tear down the current connection (if any) and reconnect in [mode].
  ///
  /// Used to switch between text and voice without losing the singleton
  /// transport. The close emits a `ws_closed` event; the reconnect re-runs the
  /// auth handshake and the chat layer resets `connected` on the next
  /// `auth_ok`.
  Future<void> reconnect(String accessToken, {required String mode}) async {
    await _sub?.cancel();
    _sub = null;
    final old = _channel;
    _channel = null;
    await old?.sink.close();
    connect(accessToken, mode: mode);
  }

  void _onData(dynamic data) {
    // Binary frames are inbound PCM audio; strings are JSON events.
    if (data is! String) {
      final bytes = _asBytes(data);
      if (bytes != null) {
        _audioFrames.add(bytes);
      }
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

  /// Normalise the various binary payload shapes a WebSocket may deliver
  /// (`Uint8List`, `List<int>`, or a `ByteBuffer`) into a `Uint8List`.
  Uint8List? _asBytes(dynamic data) {
    if (data is Uint8List) {
      return data;
    }
    if (data is ByteBuffer) {
      return data.asUint8List();
    }
    if (data is List<int>) {
      return Uint8List.fromList(data);
    }
    return null;
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

  /// Stream a chunk of captured mic PCM (16 kHz mono 16-bit LE) as a single
  /// WebSocket binary frame. No JSON wrapping.
  void sendAudio(Uint8List pcm) {
    final channel = _channel;
    if (channel == null) {
      return;
    }
    channel.sink.add(pcm);
  }

  /// Encode and write a raw JSON frame.
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
    await _audioFrames.close();
  }
}
