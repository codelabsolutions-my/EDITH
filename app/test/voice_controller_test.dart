import 'dart:convert';
import 'dart:typed_data';

import 'package:edith_app/voice/audio_io.dart';
import 'package:edith_app/voice/voice_controller.dart';
import 'package:edith_app/voice/voice_state.dart';
import 'package:edith_app/ws/ws_transport.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes/fake_audio.dart';
import 'ws_transport_test.dart' show FakeWebSocketChannel;

void main() {
  late FakeWebSocketChannel channel;
  late WsTransport transport;
  late FakeAudioCapture capture;
  late FakeAudioPlayback playback;
  late ProviderContainer container;
  late NotifierProvider<VoiceController, VoiceState> provider;

  void build({AudioException? startThrows}) {
    channel = FakeWebSocketChannel();
    transport = WsTransport(
      url: 'ws://test/ws',
      channelFactory: (_) => channel,
    );
    capture = FakeAudioCapture(startThrows: startThrows);
    playback = FakeAudioPlayback();
    provider = NotifierProvider<VoiceController, VoiceState>(
      () => VoiceController(
        captureOverride: capture,
        playbackOverride: playback,
        transportOverride: transport,
      ),
    );
    container = ProviderContainer();
  }

  tearDown(() {
    container.dispose();
    transport.dispose();
  });

  VoiceController controller() => container.read(provider.notifier);
  VoiceState read() => container.read(provider);
  Future<void> settle() => Future<void>.delayed(Duration.zero);

  test('enable starts the mic and marks capturing', () async {
    build();
    transport.connect('tok', mode: 'voice');
    await controller().enable();

    expect(capture.started, isTrue);
    expect(read().micState, MicState.capturing);
  });

  test('enable surfaces an AudioException as an error, stays not-capturing',
      () async {
    build(startThrows: const AudioException('denied'));
    await controller().enable();

    expect(read().micState, MicState.permissionNeeded);
    expect(read().errorMessage, 'denied');
  });

  test('captured frames are streamed to the transport as binary', () async {
    build();
    transport.connect('tok', mode: 'voice');
    await controller().enable();
    channel.sentFrames.clear();

    capture.emit(Uint8List.fromList([1, 2, 3, 4]));
    await settle();

    // Binary frame, not JSON-wrapped.
    expect(channel.sentFrames.single, isA<Uint8List>());
    expect(channel.sentFrames.single, [1, 2, 3, 4]);
  });

  test('inbound binary audio is enqueued for playback', () async {
    build();
    transport.connect('tok', mode: 'voice');
    await controller().enable();

    channel.emit(Uint8List.fromList([9, 9, 9, 9]));
    await settle();

    expect(playback.enqueued.single, [9, 9, 9, 9]);
  });

  test('speaking + captured frame triggers a single barge-in', () async {
    build();
    transport.connect('tok', mode: 'voice');
    await controller().enable();
    // Server says EDITH is speaking.
    channel.emit(jsonEncode({'type': 'status', 'state': 'speaking'}));
    await settle();
    channel.sentFrames.clear();
    final stopsBefore = playback.stopCount;

    // User talks over EDITH: two frames, but only one barge_in.
    capture.emit(Uint8List.fromList([1, 1]));
    capture.emit(Uint8List.fromList([2, 2]));
    await settle();

    final jsonFrames = channel.sentFrames
        .whereType<String>()
        .map((f) => jsonDecode(f))
        .toList();
    expect(
      jsonFrames.where((f) => f['type'] == 'barge_in'),
      hasLength(1),
    );
    expect(playback.stopCount, stopsBefore + 1);
    // Audio frames still flow during/after barge-in.
    expect(channel.sentFrames.whereType<Uint8List>(), hasLength(2));
  });

  test('barge-in re-arms after EDITH stops speaking', () async {
    build();
    transport.connect('tok', mode: 'voice');
    await controller().enable();

    channel.emit(jsonEncode({'type': 'status', 'state': 'speaking'}));
    await settle();
    capture.emit(Uint8List.fromList([1]));
    await settle();

    // Turn ends, then a new speaking turn.
    channel.emit(jsonEncode({'type': 'status', 'state': 'idle'}));
    channel.emit(jsonEncode({'type': 'status', 'state': 'speaking'}));
    await settle();
    final stopsBefore = playback.stopCount;
    capture.emit(Uint8List.fromList([2]));
    await settle();

    expect(playback.stopCount, stopsBefore + 1);
  });

  test('no barge-in when EDITH is not speaking', () async {
    build();
    transport.connect('tok', mode: 'voice');
    await controller().enable();
    channel.sentFrames.clear();

    capture.emit(Uint8List.fromList([1, 2]));
    await settle();

    final jsonFrames = channel.sentFrames
        .whereType<String>()
        .map((f) => jsonDecode(f));
    expect(jsonFrames.where((f) => f['type'] == 'barge_in'), isEmpty);
    expect(playback.stopCount, 0);
  });

  test('disable stops mic and playback and turns voice off', () async {
    build();
    transport.connect('tok', mode: 'voice');
    await controller().enable();

    await controller().disable();

    expect(capture.stopped, isTrue);
    expect(read().micState, MicState.off);
  });

  test('playback level drives the orb output level', () async {
    build();
    transport.connect('tok', mode: 'voice');
    controller(); // build the notifier so it subscribes
    playback.emitLevel(0.7);
    await settle();

    expect(read().outputLevel, closeTo(0.7, 0.0001));
  });
}
