import 'dart:typed_data';

/// Accumulates incoming 16-bit PCM bytes and emits them in fixed-size frames.
///
/// The browser hands capture buffers of arbitrary length; the server wants
/// ~20-40 ms chunks (640-1280 bytes at 16 kHz mono 16-bit). This buffers the
/// leftover tail across calls so no samples are dropped or split mid-sample.
class PcmFramer {
  PcmFramer({this.frameBytes = 640}) : assert(frameBytes % 2 == 0);

  /// Target frame size in bytes. 640 bytes = 320 samples = 20 ms at 16 kHz.
  final int frameBytes;

  final BytesBuilder _buffer = BytesBuilder(copy: false);

  /// Add a chunk and return any whole frames it completes.
  List<Uint8List> add(Uint8List chunk) {
    _buffer.add(chunk);
    return _drain(flush: false);
  }

  /// Emit any remaining buffered bytes as a final (possibly short) frame.
  List<Uint8List> flush() => _drain(flush: true);

  List<Uint8List> _drain({required bool flush}) {
    final frames = <Uint8List>[];
    final bytes = _buffer.takeBytes();
    var offset = 0;
    while (bytes.length - offset >= frameBytes) {
      frames.add(Uint8List.sublistView(bytes, offset, offset + frameBytes));
      offset += frameBytes;
    }
    final remaining = bytes.length - offset;
    if (flush && remaining > 0) {
      frames.add(Uint8List.sublistView(bytes, offset));
    } else if (remaining > 0) {
      _buffer.add(Uint8List.sublistView(bytes, offset));
    }
    return frames;
  }
}
