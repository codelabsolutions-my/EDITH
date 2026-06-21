import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:edith_app/ws/events.dart';
import 'package:edith_app/ws/ws_transport.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:stream_channel/stream_channel.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

/// A [WebSocketChannel] whose inbound stream and outbound sink are fully
/// controllable from the test.
class FakeWebSocketChannel extends StreamChannelMixin<dynamic>
    implements WebSocketChannel {
  FakeWebSocketChannel()
      : _inbound = StreamController<dynamic>(),
        sentFrames = <dynamic>[] {
    sink = _CapturingSink(sentFrames, _inbound);
  }

  final StreamController<dynamic> _inbound;
  final List<dynamic> sentFrames;

  /// Push a frame to the client side as if the server sent it.
  void emit(dynamic data) => _inbound.add(data);

  @override
  Stream<dynamic> get stream => _inbound.stream;

  @override
  late final WebSocketSink sink;

  @override
  int? get closeCode => null;

  @override
  String? get closeReason => null;

  @override
  String? get protocol => null;

  @override
  Future<void> get ready => Future<void>.value();

  @override
  noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _CapturingSink implements WebSocketSink {
  _CapturingSink(this._sent, this._inbound);

  final List<dynamic> _sent;
  final StreamController<dynamic> _inbound;

  @override
  void add(dynamic data) => _sent.add(data);

  @override
  Future<void> close([int? closeCode, String? closeReason]) async {
    if (!_inbound.isClosed) {
      await _inbound.close();
    }
  }

  @override
  void addError(Object error, [StackTrace? stackTrace]) {}

  @override
  Future<void> addStream(Stream<dynamic> stream) async {}

  @override
  Future<void> get done => Future<void>.value();
}

void main() {
  late FakeWebSocketChannel fake;
  late WsTransport transport;

  setUp(() {
    fake = FakeWebSocketChannel();
    transport = WsTransport(
      url: 'ws://test/ws',
      channelFactory: (_) => fake,
    );
  });

  tearDown(() => transport.dispose());

  test('connect sends the auth frame first (text mode by default)', () {
    transport.connect('tok-123');
    expect(fake.sentFrames, hasLength(1));
    final frame = jsonDecode(fake.sentFrames.single as String);
    expect(frame, {'type': 'auth', 'token': 'tok-123', 'mode': 'text'});
  });

  test('connect with mode:voice carries it in the auth frame', () {
    transport.connect('tok', mode: 'voice');
    final frame = jsonDecode(fake.sentFrames.single as String);
    expect(frame, {'type': 'auth', 'token': 'tok', 'mode': 'voice'});
  });

  test('inbound frames are decoded into typed events', () async {
    transport.connect('tok');
    final events = <InboundEvent>[];
    final sub = transport.events.listen(events.add);

    fake.emit(jsonEncode({'type': 'auth_ok', 'user': {'id': 'u1'}}));
    fake.emit(jsonEncode({
      'type': 'transcript',
      'role': 'edith',
      'text': 'hi',
      'final': false,
    }));
    fake.emit(jsonEncode({'type': 'turn_end'}));
    await Future<void>.delayed(Duration.zero);

    expect(events.map((e) => e.runtimeType).toList(), [
      AuthOkEvent,
      TranscriptEvent,
      TurnEndEvent,
    ]);
    await sub.cancel();
  });

  test('malformed JSON is ignored, not fatal', () async {
    transport.connect('tok');
    final events = <InboundEvent>[];
    final sub = transport.events.listen(events.add);

    fake.emit('not json');
    fake.emit(jsonEncode({'type': 'turn_end'}));
    await Future<void>.delayed(Duration.zero);

    expect(events.single, isA<TurnEndEvent>());
    await sub.cancel();
  });

  test('sendText / sendConfirm / sendBargeIn encode the right frames', () {
    transport.connect('tok');
    fake.sentFrames.clear();

    transport.sendText('hello');
    transport.sendConfirm(actionId: 'a1', ok: true);
    transport.sendBargeIn();

    final frames =
        fake.sentFrames.map((f) => jsonDecode(f as String)).toList();
    expect(frames, [
      {'type': 'text', 'content': 'hello'},
      {'type': 'confirm', 'action_id': 'a1', 'ok': true},
      {'type': 'barge_in'},
    ]);
  });

  test('inbound binary frames route to audioFrames, not events', () async {
    transport.connect('tok');
    final events = <InboundEvent>[];
    final audio = <Uint8List>[];
    final eSub = transport.events.listen(events.add);
    final aSub = transport.audioFrames.listen(audio.add);

    fake.emit(Uint8List.fromList([1, 2, 3, 4]));
    fake.emit(jsonEncode({'type': 'turn_end'}));
    await Future<void>.delayed(Duration.zero);

    expect(audio.single, [1, 2, 3, 4]);
    expect(events.single, isA<TurnEndEvent>());
    await eSub.cancel();
    await aSub.cancel();
  });

  test('sendAudio writes a raw binary frame (no JSON wrapping)', () {
    transport.connect('tok');
    fake.sentFrames.clear();

    transport.sendAudio(Uint8List.fromList([5, 6, 7, 8]));

    expect(fake.sentFrames.single, isA<Uint8List>());
    expect(fake.sentFrames.single, [5, 6, 7, 8]);
  });

  test('reconnect tears down and re-auths in the new mode', () async {
    // A fresh channel per connect, as the real factory does.
    final channels = <FakeWebSocketChannel>[];
    final reconnecting = WsTransport(
      url: 'ws://test/ws',
      channelFactory: (_) {
        final c = FakeWebSocketChannel();
        channels.add(c);
        return c;
      },
    );
    addTearDown(reconnecting.dispose);

    reconnecting.connect('tok', mode: 'text');
    await reconnecting.reconnect('tok', mode: 'voice');

    expect(channels, hasLength(2));
    final firstAuth = jsonDecode(channels[0].sentFrames.single as String);
    expect(firstAuth['mode'], 'text');
    final secondAuth = jsonDecode(channels[1].sentFrames.single as String);
    expect(secondAuth, {'type': 'auth', 'token': 'tok', 'mode': 'voice'});
  });
}
