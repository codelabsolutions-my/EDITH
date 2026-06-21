import 'dart:math' as math;
import 'dart:typed_data';

import 'orb_palette.dart';

/// A traveling electron: interpolates from a start to an end point over [t].
class Electron {
  Electron({
    required this.sx,
    required this.sy,
    required this.sz,
    required this.ex,
    required this.ey,
    required this.ez,
    required this.speed,
  });

  final double sx, sy, sz, ex, ey, ez;
  final double speed;
  double t = 0;
}

/// A faithful Dart port of the JARVIS particle-constellation orb physics
/// (`createOrb` in jarvis_orb.ts): N drifting 3D particles pulled toward a
/// state-dependent radius, connection lines between nearby ones, and electrons
/// that travel along connections during "thinking".
///
/// Pure simulation (no Flutter/Canvas) so the physics is unit-testable; the
/// painter reads [posX]/[posY]/[posZ], [lineCount]/[lineAx..], etc. each frame.
///
/// We only have a single audio amplitude (`level`), so both the source's `bass`
/// and `mid` are driven from it.
class OrbSimulation {
  OrbSimulation({required this.particleCount, math.Random? random})
      : _rng = random ?? math.Random(7) {
    _posX = Float32List(particleCount);
    _posY = Float32List(particleCount);
    _posZ = Float32List(particleCount);
    _velX = Float32List(particleCount);
    _velY = Float32List(particleCount);
    _velZ = Float32List(particleCount);
    _phase = Float32List(particleCount);

    for (var i = 0; i < particleCount; i++) {
      final theta = _rng.nextDouble() * math.pi * 2;
      final phi = math.acos(2 * _rng.nextDouble() - 1);
      final r = math.sqrt(_rng.nextDouble()) * 25;
      _posX[i] = r * math.sin(phi) * math.cos(theta);
      _posY[i] = r * math.sin(phi) * math.sin(theta);
      _posZ[i] = r * math.cos(phi);
      _phase[i] = _rng.nextDouble() * 1000;
    }

    // Connection line scratch buffers (segment endpoints in model space).
    _lineAx = Float32List(maxLines);
    _lineAy = Float32List(maxLines);
    _lineAz = Float32List(maxLines);
    _lineBx = Float32List(maxLines);
    _lineBy = Float32List(maxLines);
    _lineBz = Float32List(maxLines);
  }

  final int particleCount;
  final math.Random _rng;

  static const int maxLines = 8000;
  static const double lineDistance = 8;

  late final Float32List _posX, _posY, _posZ;
  late final Float32List _velX, _velY, _velZ;
  late final Float32List _phase;
  late final Float32List _lineAx, _lineAy, _lineAz, _lineBx, _lineBy, _lineBz;

  Float32List get posX => _posX;
  Float32List get posY => _posY;
  Float32List get posZ => _posZ;

  // ── Smoothed state values (lerped at 0.02 like the source) ──
  double _radius = 25, _speed = 0.3, _bright = 0.6, _size = 0.4;
  double _lineAmount = 0, _electronRate = 0;
  double _spinX = 0, _spinY = 0, _spinZ = 0;
  double _transitionEnergy = 0;
  double _cloudZ = 0, _cloudZVel = 0;
  double _time = 0;

  bool _sawState = false;
  bool _wasThinking = false, _wasSpeaking = false;
  double _colorR = 0x4c / 255, _colorG = 0xa8 / 255, _colorB = 0xe8 / 255;

  final List<Electron> _electrons = [];
  double _lastElectronSpawn = 0;
  final List<int> _connStart = []; // indices into the line buffers
  int _lineCount = 0;

  // Public read-outs for the painter.
  double get spinX => _spinX;
  double get spinY => _spinY;
  double get spinZ => _spinZ;
  double get cloudZ => _cloudZ;
  double get brightness => _bright;
  double get pointSize => _size;
  double get lineOpacity => _lineAmount * 0.12;
  int get lineCount => _lineCount;
  double lineAx(int i) => _lineAx[i];
  double lineAy(int i) => _lineAy[i];
  double lineAz(int i) => _lineAz[i];
  double lineBx(int i) => _lineBx[i];
  double lineBy(int i) => _lineBy[i];
  double lineBz(int i) => _lineBz[i];
  List<Electron> get electrons => _electrons;
  double get colorR => _colorR;
  double get colorG => _colorG;
  double get colorB => _colorB;
  double get time => _time;

  /// Advance the simulation by [dt] seconds with the current [targets] and
  /// audio [level] (0..1, used for both bass and mid).
  void step(double dt, OrbTargets targets, double level) {
    _time += dt;
    final t = _time;
    final bass = level.clamp(0.0, 1.0);
    final mid = level.clamp(0.0, 1.0);

    // Smooth toward state targets (source lerps per-frame at 0.02; scale by the
    // frame's share of a 60fps step so it's framerate-independent).
    final k = 1 - math.pow(1 - 0.02, dt * 60).toDouble();
    _radius += (targets.radius - _radius) * k;
    _speed += (targets.speed - _speed) * k;
    _bright += (targets.bright - _bright) * k;
    _size += (targets.size - _size) * k;
    _lineAmount += (targets.lineAmount - _lineAmount) * k;
    _electronRate += (targets.electronRate - _electronRate) * k;

    // Transition tumble on any state change.
    final stateChanged = !_sawState ||
        _wasThinking != targets.isThinking ||
        _wasSpeaking != targets.isSpeaking;
    if (stateChanged) {
      _transitionEnergy = 1.0;
      _sawState = true;
      _wasThinking = targets.isThinking;
      _wasSpeaking = targets.isSpeaking;
    }
    _transitionEnergy *= math.pow(0.985, dt * 60).toDouble();
    if (_transitionEnergy > 0.05) {
      _spinX += _transitionEnergy * 0.012 * math.sin(t * 1.7) * dt * 60;
      _spinY += _transitionEnergy * 0.015 * dt * 60;
      _spinZ += _transitionEnergy * 0.008 * math.cos(t * 1.3) * dt * 60;
    }

    // Depth Z breathing.
    var zTarget = math.sin(t * 0.12) * 8;
    if (targets.isThinking) {
      zTarget = math.sin(t * 0.3) * 15 + math.sin(t * 0.9) * 6;
    } else if (targets.isSpeaking) {
      zTarget = math.sin(t * 0.15) * 6 - bass * 10;
    }
    _cloudZVel += (zTarget - _cloudZ) * 0.008 * dt * 60;
    _cloudZVel *= math.pow(0.94, dt * 60).toDouble();
    _cloudZ += _cloudZVel * dt * 60;

    _stepParticles(t, bass, mid, targets.isSpeaking, dt);
    _stepLines(bass);
    _stepElectrons(t, dt);
    _stepColor(targets);
  }

  void _stepParticles(
      double t, double bass, double mid, bool speaking, double dt) {
    final frame = dt * 60; // velocities in the source are per-60fps-frame
    for (var i = 0; i < particleCount; i++) {
      final x = _posX[i], y = _posY[i], z = _posZ[i];
      final px = _phase[i];

      _velX[i] += math.sin(t * 0.05 + px) * 0.001 * _speed * frame;
      _velY[i] += math.cos(t * 0.06 + px * 1.3) * 0.001 * _speed * frame;
      _velZ[i] += math.sin(t * 0.055 + px * 0.7) * 0.001 * _speed * frame;
      _velX[i] += math.sin(t * 0.02 + px * 2.1 + y * 0.1) * 0.0008 * _speed * frame;
      _velY[i] += math.cos(t * 0.025 + px * 1.7 + z * 0.1) * 0.0008 * _speed * frame;
      _velZ[i] += math.sin(t * 0.022 + px * 0.9 + x * 0.1) * 0.0008 * _speed * frame;

      final dist = math.sqrt(x * x + y * y + z * z);
      final d = dist == 0 ? 0.01 : dist;
      final pull = (math.max(0, d - _radius) * 0.002 + 0.0003) * frame;
      _velX[i] -= (x / d) * pull;
      _velY[i] -= (y / d) * pull;
      _velZ[i] -= (z / d) * pull;

      if (bass > 0.05) {
        _velX[i] += (x / d) * bass * 0.02 * frame;
        _velY[i] += (y / d) * bass * 0.02 * frame;
        _velZ[i] += (z / d) * bass * 0.02 * frame;
      }
      if (speaking && mid > 0.1) {
        final pulse = math.sin(t * 8 + px);
        _velX[i] += (x / d) * mid * 0.012 * pulse * frame;
        _velY[i] += (y / d) * mid * 0.012 * pulse * frame;
      }

      final damp = math.pow(0.992, frame).toDouble();
      _velX[i] *= damp;
      _velY[i] *= damp;
      _velZ[i] *= damp;
      _posX[i] = x + _velX[i] * frame;
      _posY[i] = y + _velY[i] * frame;
      _posZ[i] = z + _velZ[i] * frame;
    }
  }

  void _stepLines(double bass) {
    _connStart.clear();
    if (_lineAmount <= 0.01) {
      _lineCount = 0;
      return;
    }
    final maxDist = lineDistance * (1 + bass * 0.5);
    final maxDistSq = maxDist * maxDist;
    final step = math.max(1, (particleCount / 600).floor());

    var count = 0;
    for (var i = 0; i < particleCount && count < maxLines; i += step) {
      final x1 = _posX[i], y1 = _posY[i], z1 = _posZ[i];
      for (var j = i + step; j < particleCount && count < maxLines; j += step) {
        final dx = _posX[j] - x1, dy = _posY[j] - y1, dz = _posZ[j] - z1;
        if (dx * dx + dy * dy + dz * dz < maxDistSq) {
          _lineAx[count] = x1;
          _lineAy[count] = y1;
          _lineAz[count] = z1;
          _lineBx[count] = _posX[j];
          _lineBy[count] = _posY[j];
          _lineBz[count] = _posZ[j];
          if (_connStart.length < 500) {
            _connStart.add(count);
          }
          count++;
        }
      }
    }
    _lineCount = count;
  }

  void _stepElectrons(double t, double dt) {
    // Spawn during thinking: max 3 alive, one per ~1s, 2-4s to travel.
    if (_connStart.isNotEmpty && _electronRate > 0.005) {
      if (_electrons.length < 3 && (t - _lastElectronSpawn) > 1.0) {
        final c = _connStart[_rng.nextInt(_connStart.length)];
        _electrons.add(Electron(
          sx: _lineAx[c],
          sy: _lineAy[c],
          sz: _lineAz[c],
          ex: _lineBx[c],
          ey: _lineBy[c],
          ez: _lineBz[c],
          speed: 0.003 + _rng.nextDouble() * 0.003,
        ));
        _lastElectronSpawn = t;
      }
    }
    final frame = dt * 60;
    for (var e = _electrons.length - 1; e >= 0; e--) {
      final el = _electrons[e];
      el.t += el.speed * frame;
      if (el.t >= 1) {
        _electrons.removeAt(e);
      }
    }
  }

  void _stepColor(OrbTargets targets) {
    final tc = targets.color;
    const lerp = 0.015;
    _colorR += (tc.r - _colorR) * lerp;
    _colorG += (tc.g - _colorG) * lerp;
    _colorB += (tc.b - _colorB) * lerp;
  }
}
