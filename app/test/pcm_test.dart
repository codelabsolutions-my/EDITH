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
