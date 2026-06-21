import 'package:edith_app/ui/orb/orb.dart';
import 'package:edith_app/ui/orb/orb_palette.dart';
import 'package:edith_app/ui/orb/orb_simulation.dart';
import 'package:edith_app/voice/voice_state.dart';
import 'package:edith_app/ws/events.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('OrbTargets.of', () {
    test('maps each state to the JARVIS per-state targets', () {
      final idle = OrbTargets.of(SessionState.idle, MicState.off);
      final listening =
          OrbTargets.of(SessionState.listening, MicState.capturing);
      final thinking = OrbTargets.of(SessionState.thinking, MicState.capturing);
      final speaking = OrbTargets.of(SessionState.speaking, MicState.capturing);

      // Radii shrink as the orb gets more active (28 → 22 → 16/18).
      expect(idle.radius, 28);
      expect(listening.radius, 22);
      expect(thinking.radius, 16);
      expect(speaking.radius, 18);

      // Only thinking spawns electrons and reaches full line density.
      expect(thinking.electronRate, greaterThan(0));
      expect(thinking.lineAmount, 1.0);
      expect(idle.electronRate, 0);
      expect(thinking.isThinking, isTrue);
      expect(speaking.isSpeaking, isTrue);
    });

    test('a live mic sitting idle reads as listening', () {
      final t = OrbTargets.of(SessionState.idle, MicState.capturing);
      expect(t.radius, 22);
    });
  });

  group('OrbSimulation', () {
    test('seeds particles within roughly the spawn radius', () {
      final sim = OrbSimulation(particleCount: 200);
      for (var i = 0; i < sim.posX.length; i++) {
        final r = sim.posX[i] * sim.posX[i] +
            sim.posY[i] * sim.posY[i] +
            sim.posZ[i] * sim.posZ[i];
        // Spawn radius is sqrt(rand)*25 → max ~25, allow a little slack.
        expect(r, lessThan(26.0 * 26.0));
      }
    });

    test('stepping advances time and stays finite', () {
      final sim = OrbSimulation(particleCount: 300);
      final targets = OrbTargets.of(SessionState.speaking, MicState.capturing);
      for (var i = 0; i < 120; i++) {
        sim.step(1 / 60, targets, 0.6);
      }
      expect(sim.time, greaterThan(1.9));
      for (var i = 0; i < sim.posX.length; i++) {
        expect(sim.posX[i].isFinite, isTrue);
        expect(sim.posY[i].isFinite, isTrue);
      }
    });

    test('lines appear once lineAmount ramps up', () {
      final sim = OrbSimulation(particleCount: 800);
      final thinking =
          OrbTargets.of(SessionState.thinking, MicState.capturing);
      for (var i = 0; i < 300; i++) {
        sim.step(1 / 60, thinking, 0.4);
      }
      expect(sim.lineCount, greaterThan(0));
      expect(sim.lineOpacity, greaterThan(0));
    });

    test('electrons spawn during thinking, never otherwise', () {
      final sim = OrbSimulation(particleCount: 800);
      final thinking =
          OrbTargets.of(SessionState.thinking, MicState.capturing);
      for (var i = 0; i < 360; i++) {
        sim.step(1 / 60, thinking, 0.3);
      }
      expect(sim.electrons.length, inInclusiveRange(0, 3));

      final idleSim = OrbSimulation(particleCount: 800);
      final idle = OrbTargets.of(SessionState.idle, MicState.off);
      for (var i = 0; i < 360; i++) {
        idleSim.step(1 / 60, idle, 0.0);
      }
      expect(idleSim.electrons, isEmpty);
    });
  });

  testWidgets('Orb renders and animates without crashing', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: Center(
            child: Orb(
              level: 0.5,
              sessionState: SessionState.speaking,
              micState: MicState.capturing,
              size: 160,
              particleCount: 200,
            ),
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 16));
    await tester.pump(const Duration(milliseconds: 16));

    expect(find.byType(Orb), findsOneWidget);
    expect(find.byType(CustomPaint), findsWidgets);
  });
}
