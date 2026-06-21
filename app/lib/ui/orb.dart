import 'package:flutter/material.dart';

import '../voice/voice_state.dart';
import '../ws/events.dart';

/// A simple amplitude-reactive orb: a pulsing circle whose size tracks the
/// output audio level and whose colour reflects the session state.
///
/// Deliberately lightweight (no GLSL shader) — function over polish, per spec.
class Orb extends StatelessWidget {
  const Orb({
    required this.level,
    required this.sessionState,
    required this.micState,
    super.key,
    this.size = 160,
  });

  /// Output amplitude 0..1.
  final double level;
  final SessionState sessionState;
  final MicState micState;
  final double size;

  Color _color(ColorScheme scheme) {
    switch (sessionState) {
      case SessionState.listening:
        return scheme.tertiary;
      case SessionState.thinking:
        return scheme.secondary;
      case SessionState.speaking:
        return scheme.primary;
      case SessionState.idle:
        return micState == MicState.capturing
            ? scheme.tertiary
            : scheme.outline;
    }
  }

  String _label() {
    switch (sessionState) {
      case SessionState.listening:
        return 'Listening';
      case SessionState.thinking:
        return 'Thinking';
      case SessionState.speaking:
        return 'Speaking';
      case SessionState.idle:
        return micState == MicState.capturing ? 'Listening' : 'Idle';
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final color = _color(scheme);
    // Pulse: base 60% of size, growing with level. Speaking pulses with audio;
    // listening shows a gentle steady ring.
    final pulse = 0.6 + 0.4 * level.clamp(0.0, 1.0);
    final diameter = size * pulse;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: size,
          height: size,
          child: Center(
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 80),
              width: diameter,
              height: diameter,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [color, color.withValues(alpha: 0.4)],
                ),
                boxShadow: [
                  BoxShadow(
                    color: color.withValues(alpha: 0.5),
                    blurRadius: 24 + 24 * level,
                    spreadRadius: 4 * level,
                  ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        Text(
          _label(),
          style: Theme.of(context).textTheme.labelLarge,
        ),
      ],
    );
  }
}
