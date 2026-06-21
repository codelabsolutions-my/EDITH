/// Picks the platform audio implementation at compile time.
///
/// On web -> Web Audio (getUserMedia + AudioWorklet capture, AudioContext
/// playback). Elsewhere -> stubs that throw on capture (web is the priority
/// target; native comes later).
library;

import 'audio_io.dart';

// Default (non-web) to the stubs; override with the web implementation when
// dart:js_interop is available.
import 'stub/stub_audio.dart'
    if (dart.library.js_interop) 'web/web_audio.dart' as impl;

AudioCapture createAudioCapture() => impl.createCapture();
AudioPlayback createAudioPlayback() => impl.createPlayback();
