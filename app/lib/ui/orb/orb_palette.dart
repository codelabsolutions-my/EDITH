import 'dart:ui';

import '../../voice/voice_state.dart';
import '../../ws/events.dart';

/// Per-state simulation targets for the JARVIS particle orb, ported from the
/// original `createOrb` state switch (radius/speed/brightness/size/lineAmount/
/// electronRate) plus the per-state particle colour drift target.
class OrbTargets {
  const OrbTargets({
    required this.radius,
    required this.speed,
    required this.bright,
    required this.size,
    required this.lineAmount,
    required this.electronRate,
    required this.color,
    required this.isThinking,
    required this.isSpeaking,
  });

  final double radius;
  final double speed;
  final double bright;
  final double size;
  final double lineAmount;
  final double electronRate;

  /// Particle/line colour the orb lerps toward in this state.
  final Color color;

  final bool isThinking;
  final bool isSpeaking;

  /// Colours from the JARVIS source.
  static const Color baseCyan = Color(0xFF4CA8E8);
  static const Color thinkingCyan = Color(0xFF6EC4FF);
  static const Color speakingCyan = Color(0xFF5AB8F0);
  static const Color electronWhite = Color(0xFFFFFFFF);
  static const Color background = Color(0xFF050508);

  static OrbTargets of(SessionState session, MicState mic) {
    // A live mic sitting idle between turns reads as listening.
    final listening = session == SessionState.listening ||
        (session == SessionState.idle && mic == MicState.capturing);

    switch (session) {
      case SessionState.thinking:
        return const OrbTargets(
          radius: 16,
          speed: 0.5,
          bright: 0.7,
          size: 0.3,
          lineAmount: 1.0,
          electronRate: 0.015,
          color: thinkingCyan,
          isThinking: true,
          isSpeaking: false,
        );
      case SessionState.speaking:
        return const OrbTargets(
          radius: 18,
          speed: 0.2,
          bright: 0.7,
          size: 0.4,
          lineAmount: 0.8,
          electronRate: 0,
          color: speakingCyan,
          isThinking: false,
          isSpeaking: true,
        );
      case SessionState.listening:
      case SessionState.idle:
        if (listening) {
          return const OrbTargets(
            radius: 22,
            speed: 0.3,
            bright: 0.65,
            size: 0.4,
            lineAmount: 0.4,
            electronRate: 0,
            color: baseCyan,
            isThinking: false,
            isSpeaking: false,
          );
        }
        // idle
        return const OrbTargets(
          radius: 28,
          speed: 0.2,
          bright: 0.5,
          size: 0.35,
          lineAmount: 0.15,
          electronRate: 0,
          color: baseCyan,
          isThinking: false,
          isSpeaking: false,
        );
    }
  }
}
