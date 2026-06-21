import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../chat/chat_models.dart';
import '../providers.dart';
import '../voice/voice_state.dart';
import '../ws/events.dart';
import 'orb.dart';
import 'whatsapp_assist_screen.dart';

/// The text chat surface with EDITH.
class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key});

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _inputController = TextEditingController();
  final _scrollController = ScrollController();
  ProviderSubscription<ChatState>? _confirmListener;

  ProviderSubscription<VoiceState>? _voiceStatusListener;

  @override
  void initState() {
    super.initState();
    // Surface confirm requests as a modal dialog when they appear.
    _confirmListener = ref.listenManual<ChatState>(
      chatControllerProvider,
      (previous, next) {
        final pending = next.pendingConfirm;
        if (pending != null && previous?.pendingConfirm == null) {
          _showConfirmDialog(pending);
        }
        _scrollToBottom();
      },
    );
    // Mirror voice status onto the home-screen widget.
    _voiceStatusListener = ref.listenManual<VoiceState>(
      voiceControllerProvider,
      (previous, next) {
        if (previous?.micState != next.micState ||
            previous?.sessionState != next.sessionState) {
          ref
              .read(homeWidgetServiceProvider)
              .setStatus(_widgetStatus(next));
        }
      },
    );
    // If launched from the widget's tap-to-talk, enter voice mode once ready.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (ref.read(launchedForVoiceProvider)) {
        ref.read(launchedForVoiceProvider.notifier).set(false);
        _toggleVoice();
      }
    });
  }

  String _widgetStatus(VoiceState v) {
    if (!v.isVoiceOn) {
      return 'Tap to talk';
    }
    switch (v.sessionState) {
      case SessionState.listening:
        return 'Listening…';
      case SessionState.thinking:
        return 'Thinking…';
      case SessionState.speaking:
        return 'Speaking…';
      case SessionState.idle:
        return 'Ready';
    }
  }

  @override
  void dispose() {
    _confirmListener?.close();
    _voiceStatusListener?.close();
    _inputController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  /// Flip between text and voice mode: reconnect the WS in the new mode, then
  /// start or stop the mic.
  Future<void> _toggleVoice() async {
    final voice = ref.read(voiceControllerProvider);
    final token = ref.read(accessTokenProvider);
    if (token == null) {
      return;
    }
    final transport = ref.read(wsTransportProvider);
    if (voice.isVoiceOn) {
      await ref.read(voiceControllerProvider.notifier).disable();
      // reconnect re-runs the auth handshake; the chat layer resets `connected`
      // on the next auth_ok.
      await transport.reconnect(token, mode: 'text');
    } else {
      await transport.reconnect(token, mode: 'voice');
      await ref.read(voiceControllerProvider.notifier).enable();
    }
  }

  void _send() {
    final text = _inputController.text;
    if (text.trim().isEmpty) {
      return;
    }
    ref.read(chatControllerProvider.notifier).sendText(text);
    _inputController.clear();
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
    ref
        .read(chatControllerProvider.notifier)
        .respondConfirm(ok: ok ?? false);
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(chatControllerProvider);
    final user = ref.watch(authUserProvider);
    final voice = ref.watch(voiceControllerProvider);

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
          IconButton(
            tooltip: voice.isVoiceOn ? 'Switch to text' : 'Switch to voice',
            icon: Icon(voice.isVoiceOn ? Icons.keyboard : Icons.mic),
            onPressed: _toggleVoice,
          ),
        ],
      ),
      body: Column(
        children: [
          if (state.errorMessage != null)
            _Banner(text: state.errorMessage!),
          if (voice.errorMessage != null)
            _Banner(text: voice.errorMessage!),
          if (voice.isVoiceOn)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 16),
              child: Orb(
                level: voice.outputLevel,
                sessionState: voice.sessionState,
                micState: voice.micState,
              ),
            ),
          Expanded(
            child: state.messages.isEmpty
                ? const Center(
                    child: Text('Say hi to EDITH to get started.'),
                  )
                : ListView.builder(
                    controller: _scrollController,
                    padding: const EdgeInsets.all(12),
                    itemCount: state.messages.length,
                    itemBuilder: (context, index) =>
                        _MessageBubble(message: state.messages[index]),
                  ),
          ),
          _StatusBar(state: state),
          _Composer(
            controller: _inputController,
            enabled: state.canSend,
            onSend: _send,
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
      child: Text(
        text,
        style: TextStyle(color: scheme.onErrorContainer),
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isUser = message.role == MessageRole.user;
    final color = isUser ? scheme.primaryContainer : scheme.surfaceContainerHighest;
    final onColor = isUser ? scheme.onPrimaryContainer : scheme.onSurface;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.78,
        ),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Text(
          message.text.isEmpty && message.isStreaming ? '…' : message.text,
          style: TextStyle(color: onColor),
        ),
      ),
    );
  }
}

class _StatusBar extends StatelessWidget {
  const _StatusBar({required this.state});

  final ChatState state;

  @override
  Widget build(BuildContext context) {
    final tool = state.activeTool;
    if (!state.isBusy && tool == null) {
      return const SizedBox.shrink();
    }
    final label = tool != null
        ? 'Running $tool…'
        : (state.sessionState == SessionState.speaking
            ? 'EDITH is replying…'
            : 'EDITH is thinking…');
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          const SizedBox(
            height: 14,
            width: 14,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
          const SizedBox(width: 10),
          Text(label, style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }
}

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.enabled,
    required this.onSend,
  });

  final TextEditingController controller;
  final bool enabled;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
        child: Row(
          children: [
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
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 10,
                  ),
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
      ),
    );
  }
}
