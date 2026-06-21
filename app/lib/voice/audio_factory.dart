/// Picks the platform audio implementation at compile time.
///
/// On web -> Web Audio (getUserMedia + AudioWorklet capture, AudioContext
/// playback). On native (Android/iOS/desktop) -> `record` mic stream +
/// `flutter_sound` PCM playback. The conditional import keeps web's
/// dart:js_interop code and native's dart:io code from ever compiling on the
/// other platform.
library;

import 'audio_io.dart';

// Default to the native implementation; swap to the web one when
// dart:js_interop is available (i.e. the web target).
import 'native/native_audio.dart'
    if (dart.library.js_interop) 'web/web_audio.dart' as impl;

AudioCapture createAudioCapture() => impl.createCapture();
AudioPlayback createAudioPlayback() => impl.createPlayback();
