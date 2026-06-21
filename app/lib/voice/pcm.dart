import 'dart:math' as math;
import 'dart:typed_data';

/// Pure PCM helpers shared by capture and playback.
///
/// Kept free of any browser/audio dependencies so the framing, resampling, and
/// level math are directly unit-testable.
class Pcm {
  const Pcm._();

  /// Convert normalised float samples in [-1, 1] to 16-bit signed LE PCM bytes.
  static Uint8List floatsToInt16(List<double> samples) {
    final out = Int16List(samples.length);
    for (var i = 0; i < samples.length; i++) {
      final clamped = samples[i].clamp(-1.0, 1.0);
      // Asymmetric scaling: -1.0 -> -32768, +1.0 -> 32767.
      out[i] = (clamped < 0 ? clamped * 32768 : clamped * 32767).round();
    }
    return out.buffer.asUint8List();
  }

  /// Interpret 16-bit signed **little-endian** PCM bytes as normalised float
  /// samples in [-1, 1].
  ///
  /// Reads through [ByteData.getInt16] with an explicit endian so it is correct
  /// regardless of host endianness and — unlike `Int16List.view` — never throws
  /// on an odd `offsetInBytes` (WebSocket binary frames can arrive as an
  /// unaligned view of a larger buffer).
  static Float32List int16ToFloats(Uint8List bytes) {
    final sampleCount = bytes.length ~/ 2;
    final view = ByteData.view(
      bytes.buffer,
      bytes.offsetInBytes,
      sampleCount * 2,
    );
    final out = Float32List(sampleCount);
    for (var i = 0; i < sampleCount; i++) {
      out[i] = view.getInt16(i * 2, Endian.little) / 32768.0;
    }
    return out;
  }

  /// Linearly resample mono float samples from [inputRate] to [outputRate].
  ///
  /// Browsers typically hand back 44.1/48 kHz from `getUserMedia`; the server
  /// wants 16 kHz, so capture downsamples through here.
  static Float32List resample(
    Float32List input,
    int inputRate,
    int outputRate,
  ) {
    if (inputRate == outputRate || input.isEmpty) {
      return input;
    }
    final ratio = inputRate / outputRate;
    final outLength = (input.length / ratio).floor();
    final out = Float32List(outLength);
    for (var i = 0; i < outLength; i++) {
      final srcPos = i * ratio;
      final i0 = srcPos.floor();
      final i1 = math.min(i0 + 1, input.length - 1);
      final frac = srcPos - i0;
      out[i] = input[i0] * (1 - frac) + input[i1] * frac;
    }
    return out;
  }

  /// RMS amplitude (0..1) of 16-bit PCM bytes — drives the reactive orb.
  static double rms16(Uint8List bytes) {
    final floats = int16ToFloats(bytes);
    if (floats.isEmpty) {
      return 0;
    }
    var sumSquares = 0.0;
    for (final s in floats) {
      sumSquares += s * s;
    }
    return math.sqrt(sumSquares / floats.length);
  }
}
