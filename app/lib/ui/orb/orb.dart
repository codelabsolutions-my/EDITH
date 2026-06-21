import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import '../../voice/voice_state.dart';
import '../../ws/events.dart';
import 'orb_palette.dart';
import 'orb_simulation.dart';
import 'particle_orb_painter.dart';

/// The EDITH orb: a faithful Dart port of the JARVIS particle-constellation
/// visualisation — ~N drifting cyan particles with a connection-line network,
/// white electrons during "thinking", reacting to audio level and session
/// state, over a near-black field.
///
/// The simulation runs on a [Ticker]; the painter projects it to 2D each frame.
class Orb extends StatefulWidget {
  const Orb({
    required this.level,
    required this.sessionState,
    required this.micState,
    super.key,
    this.size = 160,
    this.showLabel = true,
    this.particleCount,
  });

  /// Output amplitude 0..1 (drives the source's bass/mid reactivity).
  final double level;
  final SessionState sessionState;
  final MicState micState;
  final double size;
  final bool showLabel;

  /// Override the particle count (defaults: dense on web, lighter on mobile).
  final int? particleCount;

  /// Default particle budget: the full dense look on web, lighter on mobile to
  /// hold frame rate (the line check is O(N²) on a subsample).
  static int defaultParticleCount() {
    if (kIsWeb) {
      return 1500;
    }
    return 700;
  }

  @override
  State<Orb> createState() => _OrbState();
}

class _OrbState extends State<Orb> with SingleTickerProviderStateMixin {
  late final Ticker _ticker;
  late final OrbSimulation _sim;
  final ValueNotifier<int> _frame = ValueNotifier<int>(0);
  Duration _last = Duration.zero;

  @override
  void initState() {
    super.initState();
    _sim = OrbSimulation(
      particleCount: widget.particleCount ?? Orb.defaultParticleCount(),
    );
    _ticker = createTicker(_onTick)..start();
  }

  void _onTick(Duration elapsed) {
    var dt = (elapsed - _last).inMicroseconds / 1e6;
    _last = elapsed;
    if (dt <= 0) {
      return;
    }
    // Clamp big hitches so the physics never explodes after a stall.
    if (dt > 0.05) {
      dt = 0.05;
    }
    final targets = OrbTargets.of(widget.sessionState, widget.micState);
    _sim.step(dt, targets, widget.level);
    _frame.value++;
  }

  @override
  void dispose() {
    _ticker.dispose();
    _frame.dispose();
    super.dispose();
  }

  String _label() {
    switch (widget.sessionState) {
      case SessionState.listening:
        return 'Listening';
      case SessionState.thinking:
        return 'Thinking';
      case SessionState.speaking:
        return 'Speaking';
      case SessionState.idle:
        return widget.micState == MicState.capturing ? 'Listening' : 'Idle';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: widget.size,
          height: widget.size,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: OrbTargets.background,
            boxShadow: [
              BoxShadow(
                color: OrbTargets.baseCyan.withValues(alpha: 0.12),
                blurRadius: 40,
                spreadRadius: 4,
              ),
            ],
          ),
          clipBehavior: Clip.antiAlias,
          child: CustomPaint(
            painter: ParticleOrbPainter(sim: _sim, repaint: _frame),
            size: Size.square(widget.size),
          ),
        ),
        if (widget.showLabel) ...[
          const SizedBox(height: 12),
          Text(_label(), style: Theme.of(context).textTheme.labelLarge),
        ],
      ],
    );
  }
}
