/// Native (Android/iOS/desktop) audio factory: re-exports createCapture /
/// createPlayback used by the conditional import in `audio_factory.dart`.
library;

import '../audio_io.dart';
import 'native_audio_capture.dart';
import 'native_audio_playback.dart';

AudioCapture createCapture() => NativeAudioCapture();
AudioPlayback createPlayback() => NativeAudioPlayback();
