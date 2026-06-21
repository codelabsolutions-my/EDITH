import 'dart:async';
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

import '../audio_io.dart';
import '../pcm.dart';
import '../pcm_framer.dart';

/// The AudioWorklet processor source, registered from a Blob URL so we don't
/// need a separately-served asset file. It forwards each render quantum's mono
/// samples to the main thread as a Float32Array.
const String _workletSource = '''
class EdithCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (input && input[0]) {
      // Copy: the underlying buffer is reused across calls.
      this.port.postMessage(input[0].slice(0));
    }
    return true;
  }
}
registerProcessor('edith-capture', EdithCaptureProcessor);
''';

/// Captures mic audio on Flutter web via getUserMedia + an AudioWorklet,
/// resamples to 16 kHz, and emits fixed-size 16-bit PCM frames.
class WebAudioCapture implements AudioCapture {
  WebAudioCapture();

  web.AudioContext? _ctx;
  web.MediaStream? _stream;
  web.AudioWorkletNode? _node;
  web.MediaStreamAudioSourceNode? _sourceNode;

  final PcmFramer _framer = PcmFramer();
  final _frames = StreamController<Uint8List>.broadcast();

  /// Phase-coherent resampler from the mic's native rate to 16 kHz, kept across
  /// worklet blocks so there's no discontinuity at each 128-sample boundary.
  StreamingResampler? _resampler;

  @override
  Stream<Uint8List> get frames => _frames.stream;

  @override
  Future<bool> hasPermission() async {
    try {
      final perms = web.window.navigator.permissions;
      final status = await perms
          .query({'name': 'microphone'}.jsify() as JSObject)
          .toDart;
      return status.state == 'granted';
    } catch (_) {
      // permissions.query for microphone isn't supported everywhere; treat as
      // unknown and let start() trigger the prompt.
      return false;
    }
  }

  @override
  Future<void> start() async {
    if (_ctx != null) {
      return;
    }
    final web.MediaStream stream;
    try {
      final constraints = web.MediaStreamConstraints(audio: true.toJS);
      stream = await web.window.navigator.mediaDevices
          .getUserMedia(constraints)
          .toDart;
    } catch (e) {
      throw AudioException('microphone unavailable or denied: $e');
    }
    _stream = stream;

    final ctx = web.AudioContext();
    _ctx = ctx;
    // A context created outside a user gesture starts suspended; resume it so
    // capture actually runs. start() is itself invoked from the mic-button tap.
    await ctx.resume().toDart;
    final inputRate = ctx.sampleRate.toInt();
    _resampler = StreamingResampler(
      inputRate: inputRate,
      outputRate: AudioFormat.captureSampleRate,
    );

    // Register the worklet module from a Blob URL (a JS MIME type is required
    // or some browsers reject it).
    final blob = web.Blob(
      [_workletSource.toJS].toJS,
      web.BlobPropertyBag(type: 'application/javascript'),
    );
    final url = web.URL.createObjectURL(blob);
    await ctx.audioWorklet.addModule(url).toDart;
    // Revoke only after addModule resolves; the module text is now loaded.
    web.URL.revokeObjectURL(url);

    final node = web.AudioWorkletNode(ctx, 'edith-capture');
    _node = node;
    node.port.onmessage = (web.MessageEvent event) {
      final data = event.data;
      if (data.isA<JSFloat32Array>()) {
        _onSamples((data as JSFloat32Array).toDart, inputRate);
      }
    }.toJS;

    final sourceNode = ctx.createMediaStreamSource(stream);
    _sourceNode = sourceNode;
    sourceNode.connect(node);
    // The worklet has no output we want audible; do not connect to destination.
  }

  void _onSamples(Float32List samples, int inputRate) {
    // Phase-coherent streaming resample (NOT per-block) so consecutive worklet
    // quanta join into one continuous 16 kHz signal — otherwise ASR mishears.
    final resampled = (_resampler ??= StreamingResampler(
      inputRate: inputRate,
      outputRate: AudioFormat.captureSampleRate,
    )).process(samples);
    final bytes = Pcm.floatsToInt16(resampled);
    for (final frame in _framer.add(bytes)) {
      _frames.add(frame);
    }
  }

  @override
  Future<void> stop() async {
    for (final frame in _framer.flush()) {
      _frames.add(frame);
    }
    _sourceNode?.disconnect();
    _node?.disconnect();
    _stream?.getTracks().toDart.forEach((track) => track.stop());
    await _ctx?.close().toDart;
    _ctx = null;
    _stream = null;
    _node = null;
    _sourceNode = null;
    _resampler = null;
  }

  @override
  Future<void> dispose() async {
    await stop();
    await _frames.close();
  }
}

AudioCapture createCapture() => WebAudioCapture();
