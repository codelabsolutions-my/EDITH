import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers.dart';
import '../ws/events.dart';
import '../ws/ws_transport.dart';
import 'audio_factory.dart';
import 'audio_io.dart';
import 'voice_state.dart';

/// Orchestrates voice mode: mic capture -> transport, inbound PCM -> playback,
/// status -> orb, and barge-in when the user talks over EDITH.
///
/// Dependencies are injectable so tests drive it with fakes (no real mic).
class VoiceController extends Notifier<VoiceState> {
  VoiceController({
    AudioCapture? captureOverride,
    AudioPlayback? playbackOverride,
    WsTransport? transportOverride,
  })  : _captureOverride = captureOverride,
        _playbackOverride = playbackOverride,
        _transportOverride = transportOverride;

  // These differ in name from their constructor params (public "override"
  // names), so initializing formals don't apply.
  // ignore_for_file: prefer_initializing_formals
  final AudioCapture? _captureOverride;
  final AudioPlayback? _playbackOverride;
  final WsTransport? _transportOverride;

  late final WsTransport _transport;
  late final AudioCapture _capture;
  late final AudioPlayback _playback;

  StreamSubscription<InboundEvent>? _eventSub;
  StreamSubscription<Uint8List>? _audioInSub;
  StreamSubscription<Uint8List>? _captureSub;
  StreamSubscription<double>? _levelSub;

  /// Debounces barge-in to one trigger per speaking turn.
  bool _bargedInThisTurn = false;

  @override
  VoiceState build() {
    _transport = _transportOverride ?? ref.read(wsTransportProvider);
    _capture = _captureOverride ?? createAudioCapture();
    _playback = _playbackOverride ?? createAudioPlayback();

    _eventSub = _transport.events.listen(_onEvent);
    _audioInSub = _transport.audioFrames.listen(_playback.enqueue);
    _levelSub = _playback.level.listen((level) {
      state = state.copyWith(outputLevel: level);
    });

    ref.onDispose(() {
      _eventSub?.cancel();
      _audioInSub?.cancel();
      _captureSub?.cancel();
      _levelSub?.cancel();
      _capture.dispose();
      _playback.dispose();
    });

    return const VoiceState();
  }

  void _onEvent(InboundEvent event) {
    if (event is StatusEvent) {
      // Entering a non-speaking state resets the per-turn barge-in debounce.
      if (event.sessionState != SessionState.speaking) {
        _bargedInThisTurn = false;
      }
      state = state.copyWith(sessionState: event.sessionState);
    }
  }

  /// Turn voice mode on: acquire the mic and start streaming. Caller must have
  /// already connected the transport in `voice` mode.
  ///
  /// MUST be invoked from a user-gesture handler on web — `getUserMedia` and
  /// `AudioContext.resume()` only succeed inside a gesture. The first "Tap to
  /// talk" is that gesture.
  /// Unlock audio playback. MUST be the FIRST thing called from the tap-to-talk
  /// handler — before any `await` (WS reconnect etc.), because the browser's
  /// user-gesture activation that lets `AudioContext.resume()` succeed does not
  /// survive an awaited gap. Creating + resuming the context here, inside the
  /// gesture, is what makes EDITH's reply audible.
  Future<void> primePlayback() => _playback.prime();

  Future<void> enable() async {
    if (state.micState == MicState.capturing ||
        state.micState == MicState.starting) {
      return;
    }
    state = state.copyWith(micState: MicState.starting, clearError: true);
    // Belt-and-suspenders: prime again here too (cheap no-op if already done),
    // so callers that skip primePlayback() still get unlocked playback.
    await _playback.prime();
    try {
      await _capture.start();
    } on AudioException catch (e) {
      // Most commonly a denied browser permission.
      state = state.copyWith(
        micState: MicState.denied,
        errorMessage: e.message,
      );
      return;
    }
    _captureSub = _capture.frames.listen(_onCaptureFrame);
    state = state.copyWith(micState: MicState.capturing);
  }

  /// Turn voice mode off: stop the mic and any playback.
  Future<void> disable() async {
    await _captureSub?.cancel();
    _captureSub = null;
    await _capture.stop();
    _playback.stop();
    _bargedInThisTurn = false;
    state = state.copyWith(
      micState: MicState.off,
      sessionState: SessionState.idle,
      outputLevel: 0,
    );
  }

  void _onCaptureFrame(Uint8List frame) {
    // Barge-in: if EDITH is speaking and the user is talking, cancel playback.
    if (shouldBargeIn(
      sessionState: state.sessionState,
      alreadyBargedIn: _bargedInThisTurn,
    )) {
      _bargedInThisTurn = true;
      _playback.stop();
      _transport.sendBargeIn();
    }
    _transport.sendAudio(frame);
  }
}
