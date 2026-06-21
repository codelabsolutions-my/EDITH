import 'dart:typed_data';

import 'package:edith_app/voice/pcm_framer.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('PcmFramer', () {
    test('emits whole frames and buffers the remainder', () {
      final framer = PcmFramer(frameBytes: 4);
      // 6 bytes -> one 4-byte frame, 2 buffered.
      final frames = framer.add(Uint8List.fromList([1, 2, 3, 4, 5, 6]));
      expect(frames, hasLength(1));
      expect(frames.single, [1, 2, 3, 4]);
    });

    test('completes a frame across two adds', () {
      final framer = PcmFramer(frameBytes: 4);
      expect(framer.add(Uint8List.fromList([1, 2])), isEmpty);
      final frames = framer.add(Uint8List.fromList([3, 4, 5]));
      expect(frames, hasLength(1));
      expect(frames.single, [1, 2, 3, 4]);
    });

    test('splits a large add into multiple frames', () {
      final framer = PcmFramer(frameBytes: 2);
      final frames = framer.add(Uint8List.fromList([1, 2, 3, 4, 5, 6]));
      expect(frames, hasLength(3));
      expect(frames.map((f) => f.toList()), [
        [1, 2],
        [3, 4],
        [5, 6],
      ]);
    });

    test('flush emits the buffered tail', () {
      final framer = PcmFramer(frameBytes: 4);
      framer.add(Uint8List.fromList([1, 2, 3, 4, 5, 6]));
      final tail = framer.flush();
      expect(tail, hasLength(1));
      expect(tail.single, [5, 6]);
    });

    test('flush with no remainder emits nothing', () {
      final framer = PcmFramer(frameBytes: 2);
      framer.add(Uint8List.fromList([1, 2, 3, 4]));
      expect(framer.flush(), isEmpty);
    });

    test('default frame is 640 bytes (20 ms @ 16 kHz)', () {
      final framer = PcmFramer();
      final frames = framer.add(Uint8List(1280));
      expect(frames, hasLength(2));
      expect(frames.first.length, 640);
    });
  });
}
