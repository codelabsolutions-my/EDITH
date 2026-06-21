import 'dart:typed_data';

import 'package:edith_app/voice/pcm.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Pcm.floatsToInt16 / int16ToFloats', () {
    test('round-trips representative values', () {
      final bytes = Pcm.floatsToInt16([0.0, 1.0, -1.0, 0.5]);
      // 4 samples * 2 bytes.
      expect(bytes.length, 8);

      final view = Int16List.view(bytes.buffer);
      expect(view[0], 0);
      expect(view[1], 32767); // +1.0 -> max
      expect(view[2], -32768); // -1.0 -> min
      expect(view[3], closeTo(16383, 1));
    });

    test('int16ToFloats inverts the mapping', () {
      final bytes = Pcm.floatsToInt16([0.25, -0.5]);
      final floats = Pcm.int16ToFloats(bytes);
      expect(floats[0], closeTo(0.25, 0.001));
      expect(floats[1], closeTo(-0.5, 0.001));
    });

    test('clamps out-of-range floats', () {
      final bytes = Pcm.floatsToInt16([2.0, -3.0]);
      final view = Int16List.view(bytes.buffer);
      expect(view[0], 32767);
      expect(view[1], -32768);
    });

    test('int16ToFloats tolerates an odd trailing byte', () {
      final floats = Pcm.int16ToFloats(Uint8List.fromList([0, 0, 1]));
      expect(floats.length, 1); // dangling byte dropped
    });

    test('int16ToFloats decodes an unaligned (odd-offset) view', () {
      // Simulate a WS binary frame that is an odd-offset slice of a buffer;
      // Int16List.view would throw here, ByteData-based decode must not.
      final backing = Uint8List.fromList([0xFF, 0x00, 0x00, 0x00, 0x80]);
      final view = Uint8List.sublistView(backing, 1); // offsetInBytes == 1
      expect(view.offsetInBytes.isOdd, isTrue);
      final floats = Pcm.int16ToFloats(view);
      expect(floats.length, 2);
      expect(floats[0], closeTo(0.0, 0.001)); // 0x0000
      expect(floats[1], closeTo(-1.0, 0.001)); // 0x8000 LE -> -32768
    });

    test('int16ToFloats reads little-endian regardless of value', () {
      // 0x00 0x01 LE == 256.
      final floats = Pcm.int16ToFloats(Uint8List.fromList([0x00, 0x01]));
      expect(floats[0], closeTo(256 / 32768.0, 0.0001));
    });
  });

  group('Pcm.resample', () {
    test('returns the input unchanged when rates match', () {
      final input = Float32List.fromList([0.1, 0.2, 0.3]);
      expect(Pcm.resample(input, 16000, 16000), same(input));
    });

    test('downsamples 48k -> 16k by a factor of 3 in length', () {
      final input = Float32List(48); // 1 ms at 48k
      final out = Pcm.resample(input, 48000, 16000);
      expect(out.length, 16);
    });

    test('linear interpolation halves the sample count for 2:1', () {
      final input = Float32List.fromList([0.0, 1.0, 0.0, 1.0]);
      final out = Pcm.resample(input, 2, 1);
      expect(out.length, 2);
      expect(out[0], closeTo(0.0, 0.001));
    });

    test('empty input yields empty output', () {
      expect(Pcm.resample(Float32List(0), 48000, 16000), isEmpty);
    });
  });

  group('StreamingResampler', () {
    test('passes blocks through unchanged when rates match', () {
      final r = StreamingResampler(inputRate: 16000, outputRate: 16000);
      final block = Float32List.fromList([0.1, 0.2, 0.3]);
      expect(r.process(block), same(block));
    });

    test('total output count matches a whole-signal 3:1 downsample', () {
      // 48k -> 16k of 480 samples (10ms) split into 128-sample worklet quanta.
      final signal = Float32List(480);
      for (var i = 0; i < signal.length; i++) {
        signal[i] = (i % 7) / 7.0; // arbitrary non-trivial content
      }
      final streaming = StreamingResampler(inputRate: 48000, outputRate: 16000);
      var total = 0;
      for (var off = 0; off < signal.length; off += 128) {
        final end = (off + 128) > signal.length ? signal.length : off + 128;
        total += streaming.process(Float32List.sublistView(signal, off, end)).length;
      }
      // ~480/3 = 160 output samples; per-block resampling would lose ~1 sample
      // per block (floor(128/3) repeatedly) and drift. Allow ±1 for end effects.
      expect(total, closeTo(160, 1));
    });

    test('is phase-coherent: blockwise ≈ whole-signal resample of a ramp', () {
      // A linear ramp resampled correctly stays a linear ramp; a per-block
      // resampler would kink at every block edge.
      final ramp = Float32List(384);
      for (var i = 0; i < ramp.length; i++) {
        ramp[i] = i / ramp.length;
      }
      final streaming = StreamingResampler(inputRate: 48000, outputRate: 16000);
      final out = <double>[];
      for (var off = 0; off < ramp.length; off += 128) {
        out.addAll(
          streaming.process(Float32List.sublistView(ramp, off, off + 128)),
        );
      }
      // Output should itself be (close to) a monotonic linear ramp — verify
      // consecutive deltas are uniform (no per-block discontinuity/kink).
      final deltas = [
        for (var i = 1; i < out.length; i++) out[i] - out[i - 1],
      ];
      final avg = deltas.reduce((a, b) => a + b) / deltas.length;
      for (final d in deltas) {
        expect(d, closeTo(avg, 0.002),
            reason: 'a phase-coherent ramp has uniform step; a kink means the '
                'resampler restarted phase at a block boundary');
      }
    });
  });

  group('Pcm.rms16', () {
    test('silence is zero', () {
      final bytes = Pcm.floatsToInt16(List<double>.filled(100, 0));
      expect(Pcm.rms16(bytes), closeTo(0.0, 0.0001));
    });

    test('full-scale square wave is near 1', () {
      final bytes = Pcm.floatsToInt16(List<double>.filled(100, 1.0));
      expect(Pcm.rms16(bytes), closeTo(1.0, 0.001));
    });

    test('empty bytes are zero', () {
      expect(Pcm.rms16(Uint8List(0)), 0);
    });
  });
}
