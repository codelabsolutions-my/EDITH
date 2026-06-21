/// Web audio factory: re-exports the createCapture / createPlayback used by
/// the conditional import in `audio_factory.dart`.
library;

export 'web_audio_capture.dart' show createCapture;
export 'web_audio_playback.dart' show createPlayback;
