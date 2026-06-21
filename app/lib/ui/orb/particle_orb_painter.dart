import 'dart:math' as math;
import 'package:flutter/material.dart';

import 'orb_palette.dart';
import 'orb_simulation.dart';

/// Renders the [OrbSimulation] to a 2D canvas with a perspective projection,
/// emulating the Three.js look: additive cyan particles, a connection-line
/// network, and bright white electrons, over a near-black field.
class ParticleOrbPainter extends CustomPainter {
  ParticleOrbPainter({required this.sim, required this.repaint})
      : super(repaint: repaint);

  final OrbSimulation sim;
  final Listenable repaint;

  // Perspective: camera at z=80 looking at the cloud, FOV ~45° (matches source).
  static const double _camZ = 80;

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    // Focal length chosen so the ~25-unit-radius cloud (at camDist ≈ 80) fills
    // most of the widget: persp = focal/camDist, want 25*persp ≈ 0.42*half.
    final focal = size.shortestSide * 1.35;

    // Slow camera orbit from the source (sin/cos drift), applied as a 2D offset.
    final t = sim.time;
    final camOffX = math.sin(t * 0.02) * 5;
    final camOffY = math.cos(t * 0.03) * 3;

    final cosX = math.cos(sim.spinX), sinX = math.sin(sim.spinX);
    final cosY = math.cos(sim.spinY), sinY = math.sin(sim.spinY);
    final cosZ = math.cos(sim.spinZ), sinZ = math.sin(sim.spinZ);

    // Project a model-space point to screen; returns null if behind the camera.
    Offset? project(double x, double y, double z, [List<double>? depthOut]) {
      // Rotate (X then Y then Z), matching three.js euler order roughly.
      var ry = y * cosX - z * sinX;
      var rz = y * sinX + z * cosX;
      var rx = x;
      final rx2 = rx * cosY + rz * sinY;
      rz = -rx * sinY + rz * cosY;
      rx = rx2;
      final rx3 = rx * cosZ - ry * sinZ;
      ry = rx * sinZ + ry * cosZ;
      rx = rx3;

      rz += sim.cloudZ; // cloud depth
      final camDist = _camZ - rz;
      if (camDist <= 1) {
        return null;
      }
      // Perspective divide.
      final persp = focal / camDist;
      final sx = center.dx + (rx - camOffX) * persp;
      final sy = center.dy - (ry - camOffY) * persp;
      depthOut?.add(camDist);
      return Offset(sx, sy);
    }

    final color = Color.from(
      alpha: 1,
      red: sim.colorR.clamp(0.0, 1.0),
      green: sim.colorG.clamp(0.0, 1.0),
      blue: sim.colorB.clamp(0.0, 1.0),
    );

    // ── Connection lines (additive glow) ──
    if (sim.lineOpacity > 0.004 && sim.lineCount > 0) {
      final linePaint = Paint()
        ..blendMode = BlendMode.plus
        ..strokeWidth = 1.0
        ..color = color.withValues(alpha: (sim.lineOpacity * 3).clamp(0.0, 0.6));
      for (var i = 0; i < sim.lineCount; i++) {
        final a = project(sim.lineAx(i), sim.lineAy(i), sim.lineAz(i));
        final b = project(sim.lineBx(i), sim.lineBy(i), sim.lineBz(i));
        if (a != null && b != null) {
          canvas.drawLine(a, b, linePaint);
        }
      }
    }

    // ── Particles (additive, depth-scaled) ──
    final pPaint = Paint()..blendMode = BlendMode.plus;
    final n = sim.posX.length;
    for (var i = 0; i < n; i++) {
      final depth = <double>[];
      final p = project(sim.posX[i], sim.posY[i], sim.posZ[i], depth);
      if (p == null) {
        continue;
      }
      final camDist = depth.first;
      // Nearer particles are larger/brighter (sizeAttenuation).
      final atten = (90 / camDist).clamp(0.3, 2.2);
      final radius =
          (sim.pointSize * 3.2 * atten * (size.shortestSide / 220))
              .clamp(0.5, 4.5);
      pPaint.color = color.withValues(
        alpha: (sim.brightness * (0.4 + 0.6 * (atten / 2.2))).clamp(0.0, 1.0),
      );
      canvas.drawCircle(p, radius, pPaint);
    }

    // ── Electrons (bright white, additive) ──
    if (sim.electrons.isNotEmpty) {
      final ePaint = Paint()
        ..blendMode = BlendMode.plus
        ..color = OrbTargets.electronWhite;
      for (final e in sim.electrons) {
        final x = e.sx + (e.ex - e.sx) * e.t;
        final y = e.sy + (e.ey - e.sy) * e.t;
        final z = e.sz + (e.ez - e.sz) * e.t;
        final depth = <double>[];
        final p = project(x, y, z, depth);
        if (p == null) {
          continue;
        }
        final atten = (90 / depth.first).clamp(0.4, 2.5);
        // Glow halo + bright core.
        ePaint.color = OrbTargets.electronWhite.withValues(alpha: 0.25);
        canvas.drawCircle(p, 4.0 * atten, ePaint);
        ePaint.color = OrbTargets.electronWhite;
        canvas.drawCircle(p, 1.6 * atten, ePaint);
      }
    }
  }

  @override
  bool shouldRepaint(ParticleOrbPainter old) => false; // repaint via Listenable
}
