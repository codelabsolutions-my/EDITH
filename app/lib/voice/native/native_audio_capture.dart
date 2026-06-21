import 'dart:async';
import 'dart:typed_data';

import 'package:record/record.dart';

import '../audio_io.dart';
import '../pcm_framer.dart';

/// Native mic capture (Android/iOS/desktop) via the `record` package.
///
/// Unlike the browser, native platforms honour a 16 kHz PCM16 mono request, so
/// no resampling is needed — `record` streams raw PCM which we just re-frame to
/// the server's ~20 ms chunk size.
class NativeAudioCapture implements AudioCapture {
  NativeAudioCapture({AudioRecorder? recorder})
      : _recorder = recorder ?? AudioRecorder();

  final AudioRecorder _recorder;
  final PcmFramer _framer = PcmFramer();
  final _frames = StreamController<Uint8List>.broadcast();
  StreamSubscription<Uint8List>? _recordSub;

  @override
  Stream<Uint8List> get frames => _frames.stream;

  @override
  Future<bool> hasPermission() => _recorder.hasPermission();

  @override
  Future<void> start() async {
    if (!await _recorder.hasPermission()) {
      throw const AudioException('microphone permission denied');
    }
    final Stream<Uint8List> stream;
    try {
      stream = await _recorder.startStream(
        const RecordConfig(
          encoder: AudioEncoder.pcm16bits,
          sampleRate: AudioFormat.captureSampleRate,
          numChannels: AudioFormat.channels,
        ),
      );
    } catch (e) {
      throw AudioException('failed to start mic: $e');
    }
    _recordSub = stream.listen((chunk) {
      for (final frame in _framer.add(chunk)) {
        _frames.add(frame);
      }
    });
  }

  @override
  Future<void> stop() async {
    await _recordSub?.cancel();
    _recordSub = null;
    for (final frame in _framer.flush()) {
      _frames.add(frame);
    }
    await _recorder.stop();
  }

  @override
  Future<void> dispose() async {
    await stop();
    await _recorder.dispose();
    await _frames.close();
  }
}
