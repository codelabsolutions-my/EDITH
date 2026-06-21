import 'package:flutter/material.dart';

import '../../chat/chat_models.dart';

/// A single conversation bubble in EDITH's HUD style.
///
/// User turns are solid violet, right-aligned; EDITH replies are a translucent
/// surface with a cyan accent edge, left-aligned. While EDITH streams, a soft
/// blinking caret trails the text.
class MessageBubble extends StatelessWidget {
  const MessageBubble({required this.message, super.key, this.maxWidthFactor = 0.78});

  final ChatMessage message;
  final double maxWidthFactor;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isUser = message.role == MessageRole.user;

    final BoxDecoration decoration;
    final Color textColor;
    if (isUser) {
      decoration = BoxDecoration(
        color: scheme.primary,
        borderRadius: const BorderRadius.only(
          topLeft: Radius.circular(16),
          topRight: Radius.circular(16),
          bottomLeft: Radius.circular(16),
          bottomRight: Radius.circular(4),
        ),
      );
      textColor = scheme.onPrimary;
    } else {
      decoration = BoxDecoration(
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.7),
        borderRadius: const BorderRadius.only(
          topLeft: Radius.circular(16),
          topRight: Radius.circular(16),
          bottomLeft: Radius.circular(4),
          bottomRight: Radius.circular(16),
        ),
        border: Border(
          left: BorderSide(color: scheme.secondary, width: 2),
        ),
      );
      textColor = scheme.onSurface;
    }

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 5),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * maxWidthFactor,
        ),
        decoration: decoration,
        child: _BubbleText(
          text: message.text,
          streaming: message.isStreaming,
          color: textColor,
          accent: scheme.secondary,
        ),
      ),
    );
  }
}

class _BubbleText extends StatelessWidget {
  const _BubbleText({
    required this.text,
    required this.streaming,
    required this.color,
    required this.accent,
  });

  final String text;
  final bool streaming;
  final Color color;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    final style = TextStyle(color: color, height: 1.35, fontSize: 15);
    if (!streaming) {
      return Text(text.isEmpty ? '…' : text, style: style);
    }
    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Flexible(child: Text(text.isEmpty ? '' : text, style: style)),
        _Caret(color: accent),
      ],
    );
  }
}

/// A soft blinking caret shown while a reply streams in.
class _Caret extends StatefulWidget {
  const _Caret({required this.color});

  final Color color;

  @override
  State<_Caret> createState() => _CaretState();
}

class _CaretState extends State<_Caret> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _controller.drive(
        TweenSequence<double>([
          TweenSequenceItem(tween: ConstantTween(1.0), weight: 50),
          TweenSequenceItem(tween: ConstantTween(0.0), weight: 50),
        ]),
      ),
      child: Container(
        width: 7,
        height: 16,
        margin: const EdgeInsets.only(left: 3, bottom: 2),
        decoration: BoxDecoration(
          color: widget.color,
          borderRadius: BorderRadius.circular(2),
        ),
      ),
    );
  }
}
