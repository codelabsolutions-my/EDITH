import '../ws/events.dart';

/// Whether voice mode is engaged and what the mic is doing.
enum MicState {
  /// Voice mode off (text-only).
  off,

  /// Voice mode on, mic permission pending/denied.
  permissionNeeded,

  /// Mic live and streaming.
  capturing,

  /// Voice mode on but mic temporarily paused (e.g. error).
  paused,
}

/// Snapshot of the voice subsystem for the UI (orb + mic button).
class VoiceState {
  const VoiceState({
    this.micState = MicState.off,
    this.sessionState = SessionState.idle,
    this.outputLevel = 0,
    this.errorMessage,
  });

  final MicState micState;

  /// Server-reported turn state; drives the orb colour/label.
  final SessionState sessionState;

  /// Latest playback amplitude (0..1) for the reactive orb.
  final double outputLevel;

  final String? errorMessage;

  bool get isVoiceOn => micState != MicState.off;

  /// EDITH is actively producing audio.
  bool get isSpeaking => sessionState == SessionState.speaking;

  VoiceState copyWith({
    MicState? micState,
    SessionState? sessionState,
    double? outputLevel,
    String? errorMessage,
    bool clearError = false,
  }) {
    return VoiceState(
      micState: micState ?? this.micState,
      sessionState: sessionState ?? this.sessionState,
      outputLevel: outputLevel ?? this.outputLevel,
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
    );
  }
}

/// Pure decision: should a captured mic frame trigger barge-in?
///
/// Barge-in fires when EDITH is currently speaking — the user talking over
/// playback should cancel it. Returns true at most meaningfully once per
/// speaking turn; callers track [alreadyBargedIn] to debounce.
bool shouldBargeIn({
  required SessionState sessionState,
  required bool alreadyBargedIn,
}) {
  return sessionState == SessionState.speaking && !alreadyBargedIn;
}
