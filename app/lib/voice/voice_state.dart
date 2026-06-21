import '../ws/events.dart';

/// Whether voice mode is engaged and what the mic is doing.
enum MicState {
  /// Voice mode off (text-only) — the landing state before the first tap.
  off,

  /// Acquiring the mic / awaiting the browser permission prompt.
  starting,

  /// Mic permission was denied; the UI should explain and offer text.
  denied,

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

  /// Mic is engaged (or coming up). False for the off landing state and a hard
  /// permission denial.
  bool get isVoiceOn =>
      micState == MicState.starting ||
      micState == MicState.capturing ||
      micState == MicState.paused;

  /// Live and streaming mic audio.
  bool get isCapturing => micState == MicState.capturing;

  /// Permission was refused — the UI should explain and steer to text.
  bool get isDenied => micState == MicState.denied;

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
