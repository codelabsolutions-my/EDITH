import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../chat/chat_models.dart';
import '../providers.dart';
import '../voice/voice_state.dart';
import '../ws/events.dart';
import 'orb/orb.dart';
import 'whatsapp_assist_screen.dart';
import 'widgets/message_bubble.dart';

/// The voice-first landing screen shown after login.
///
/// The Orb is front and centre; a single prominent "Tap to talk" affordance is
/// the user gesture that — on the first tap — requests mic permission, resumes
/// the AudioContext, opens the voice WS, and starts capturing. Thereafter it's
/// hands-conversational. Text stays available behind a small "type instead"
/// affordance, and a denied mic is handled gracefully.
class VoiceScreen extends ConsumerStatefulWidget {
  const VoiceScreen({super.key});

  @override
  ConsumerState<VoiceScreen> createState() => _VoiceScreenState();
}

class _VoiceScreenState extends ConsumerState<VoiceScreen> {
  final _inputController = TextEditingController();
  bool _showText = false;
  ProviderSubscription<ChatState>? _confirmListener;
  ProviderSubscription<VoiceState>? _voiceStatusListener;

  @override
  void initState() {
    super.initState();
    _confirmListener = ref.listenManual<ChatState>(
      chatControllerProvider,
      (previous, next) {
        final pending = next.pendingConfirm;
        if (pending != null && previous?.pendingConfirm == null) {
          _showConfirmDialog(pending);
        }
      },
    );
    _voiceStatusListener = ref.listenManual<VoiceState>(
      voiceControllerProvider,
      (previous, next) {
        if (previous?.micState != next.micState ||
            previous?.sessionState != next.sessionState) {
          ref.read(homeWidgetServiceProvider).setStatus(_statusLabel(next));
        }
      },
    );
    // Auto-start if launched from the home-screen widget's tap-to-talk (the
    // launcher tap is itself the required user gesture).
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (ref.read(launchedForVoiceProvider)) {
        ref.read(launchedForVoiceProvider.notifier).set(false);
        _startVoice();
      }
    });
  }

  @override
  void dispose() {
    _confirmListener?.close();
    _voiceStatusListener?.close();
    _inputController.dispose();
    super.dispose();
  }

  /// The first-tap gesture: connect the WS in voice mode, then start the mic.
  /// Both getUserMedia and AudioContext.resume() require this gesture on web.
  Future<void> _startVoice() async {
    final token = ref.read(accessTokenProvider);
    if (token == null) {
      return;
    }
    final voice = ref.read(voiceControllerProvider.notifier);
    // Unlock playback FIRST, synchronously within the tap gesture — before the
    // awaited WS reconnect, which would otherwise consume the gesture
    // activation and leave the AudioContext suspended (silent).
    // ignore: unawaited_futures
    voice.primePlayback();
    await ref.read(wsTransportProvider).reconnect(token, mode: 'voice');
    await voice.enable();
  }

  Future<void> _stopVoice() async {
    await ref.read(voiceControllerProvider.notifier).disable();
    final token = ref.read(accessTokenProvider);
    if (token != null) {
      // Drop back to a text-mode connection so typed turns still work.
      await ref.read(wsTransportProvider).reconnect(token, mode: 'text');
    }
  }

  void _sendText() {
    final text = _inputController.text;
    if (text.trim().isEmpty) {
      return;
    }
    ref.read(chatControllerProvider.notifier).sendText(text);
    _inputController.clear();
  }

  String _statusLabel(VoiceState v) {
    if (v.isDenied) {
      return 'Mic blocked';
    }
    switch (v.micState) {
      case MicState.off:
        return 'Tap to talk';
      case MicState.starting:
        return 'Starting…';
      case MicState.denied:
        return 'Mic blocked';
      case MicState.capturing:
      case MicState.paused:
        switch (v.sessionState) {
          case SessionState.listening:
          case SessionState.idle:
            return 'Listening';
          case SessionState.thinking:
            return 'Thinking…';
          case SessionState.speaking:
            return 'Speaking…';
        }
    }
  }

  Future<void> _showConfirmDialog(PendingConfirm pending) async {
    final ok = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        title: const Text('Confirm action'),
        content: Text(pending.summary),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('No'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Yes'),
          ),
        ],
      ),
    );
    ref.read(chatControllerProvider.notifier).respondConfirm(ok: ok ?? false);
  }

  @override
  Widget build(BuildContext context) {
    final voice = ref.watch(voiceControllerProvider);
    final chat = ref.watch(chatControllerProvider);
    final user = ref.watch(authUserProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(user?.displayName.isNotEmpty == true
            ? 'EDITH — ${user!.displayName}'
            : 'EDITH'),
        actions: [
          if (ref.watch(whatsAppAssistProvider).isSupported)
            IconButton(
              tooltip: 'WhatsApp assist',
              icon: const Icon(Icons.chat),
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => const WhatsAppAssistScreen(),
                ),
              ),
            ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            if (chat.errorMessage != null) _Banner(text: chat.errorMessage!),
            Expanded(
              child: Center(
                child: SingleChildScrollView(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _OrbControl(
                        voice: voice,
                        label: _statusLabel(voice),
                        onStart: _startVoice,
                        onStop: _stopVoice,
                      ),
                      if (voice.isDenied) _DeniedHelp(onUseText: _openText),
                      const SizedBox(height: 16),
                      _LatestTranscript(messages: chat.messages),
                    ],
                  ),
                ),
              ),
            ),
            _TextAffordance(
              expanded: _showText,
              controller: _inputController,
              enabled: chat.canSend,
              onToggle: () => setState(() => _showText = !_showText),
              onSend: _sendText,
            ),
          ],
        ),
      ),
    );
  }

  void _openText() => setState(() => _showText = true);
}

/// The tappable orb + primary affordance. Tapping when off starts voice;
/// tapping when live offers stop/mute.
class _OrbControl extends StatelessWidget {
  const _OrbControl({
    required this.voice,
    required this.label,
    required this.onStart,
    required this.onStop,
  });

  final VoiceState voice;
  final String label;
  final VoidCallback onStart;
  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    final isLive = voice.isCapturing || voice.micState == MicState.starting;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        GestureDetector(
          onTap: voice.micState == MicState.off || voice.isDenied
              ? onStart
              : null,
          child: Orb(
            level: voice.outputLevel,
            sessionState: voice.sessionState,
            micState: voice.micState,
            size: 220,
            showLabel: false,
          ),
        ),
        const SizedBox(height: 8),
        Text(label, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 16),
        if (!isLive && !voice.isDenied)
          FilledButton.icon(
            onPressed: onStart,
            icon: const Icon(Icons.mic),
            label: const Text('Tap to talk'),
          )
        else if (isLive)
          OutlinedButton.icon(
            onPressed: onStop,
            icon: const Icon(Icons.stop),
            label: const Text('Stop'),
          ),
      ],
    );
  }
}

class _DeniedHelp extends StatelessWidget {
  const _DeniedHelp({required this.onUseText});

  final VoidCallback onUseText;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 12),
      child: Column(
        children: [
          Text(
            'Microphone access is blocked. Allow it in your browser/site '
            'settings to talk, or type to EDITH instead.',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 8),
          TextButton(onPressed: onUseText, child: const Text('Type instead')),
        ],
      ),
    );
  }
}

/// Shows EDITH's latest reply / the last user turn under the orb.
class _LatestTranscript extends StatelessWidget {
  const _LatestTranscript({required this.messages});

  final List<ChatMessage> messages;

  @override
  Widget build(BuildContext context) {
    if (messages.isEmpty) {
      return const SizedBox.shrink();
    }
    final recent = messages.length > 4
        ? messages.sublist(messages.length - 4)
        : messages;
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 520),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Column(
          children: [
            for (final m in recent)
              MessageBubble(message: m, maxWidthFactor: 0.62),
          ],
        ),
      ),
    );
  }
}

/// A collapsed "type instead" affordance that expands into a text composer.
class _TextAffordance extends StatelessWidget {
  const _TextAffordance({
    required this.expanded,
    required this.controller,
    required this.enabled,
    required this.onToggle,
    required this.onSend,
  });

  final bool expanded;
  final TextEditingController controller;
  final bool enabled;
  final VoidCallback onToggle;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    if (!expanded) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: TextButton.icon(
          onPressed: onToggle,
          icon: const Icon(Icons.keyboard),
          label: const Text('Type instead'),
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
      child: Row(
        children: [
          IconButton(
            tooltip: 'Hide text',
            icon: const Icon(Icons.keyboard_hide),
            onPressed: onToggle,
          ),
          Expanded(
            child: TextField(
              controller: controller,
              enabled: enabled,
              minLines: 1,
              maxLines: 4,
              textInputAction: TextInputAction.send,
              onSubmitted: enabled ? (_) => onSend() : null,
              decoration: InputDecoration(
                hintText: enabled ? 'Message EDITH…' : 'Please wait…',
                border: const OutlineInputBorder(),
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              ),
            ),
          ),
          const SizedBox(width: 8),
          IconButton.filled(
            onPressed: enabled ? onSend : null,
            icon: const Icon(Icons.send),
          ),
        ],
      ),
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      color: scheme.errorContainer,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Text(text, style: TextStyle(color: scheme.onErrorContainer)),
    );
  }
}
