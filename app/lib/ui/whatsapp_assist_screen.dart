import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers.dart';
import '../whatsapp/whatsapp_message.dart';

/// Android-only settings + live view for WhatsApp personal assist.
///
/// Shows whether notification-listener access is granted (with a button to
/// open the system settings) and streams captured incoming messages, each with
/// a quick reply. On non-Android platforms it explains the feature is
/// unavailable.
class WhatsAppAssistScreen extends ConsumerWidget {
  const WhatsAppAssistScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final assist = ref.watch(whatsAppAssistProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('WhatsApp assist')),
      body: !assist.isSupported
          ? const _Unsupported()
          : Column(
              children: [
                const _PermissionCard(),
                const Divider(height: 1),
                Expanded(
                  child: StreamBuilder<WhatsAppMessage>(
                    stream: assist.incoming,
                    builder: (context, snapshot) {
                      // A real app accumulates a list; this scaffold shows the
                      // latest captured message to prove the channel wiring.
                      final msg = snapshot.data;
                      if (msg == null) {
                        return const Center(
                          child: Text('Waiting for WhatsApp messages…'),
                        );
                      }
                      return _MessageTile(message: msg);
                    },
                  ),
                ),
              ],
            ),
    );
  }
}

class _Unsupported extends StatelessWidget {
  const _Unsupported();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Padding(
        padding: EdgeInsets.all(24),
        child: Text(
          'WhatsApp assist is an Android-only feature (reads notifications via '
          'the on-device NotificationListener). It is not available on this '
          'platform.',
          textAlign: TextAlign.center,
        ),
      ),
    );
  }
}

class _PermissionCard extends ConsumerStatefulWidget {
  const _PermissionCard();

  @override
  ConsumerState<_PermissionCard> createState() => _PermissionCardState();
}

class _PermissionCardState extends ConsumerState<_PermissionCard> {
  bool? _granted;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    final granted = await ref.read(whatsAppAssistProvider).hasPermission();
    if (mounted) {
      setState(() => _granted = granted);
    }
  }

  @override
  Widget build(BuildContext context) {
    final granted = _granted;
    return ListTile(
      leading: Icon(
        granted == true ? Icons.check_circle : Icons.error_outline,
        color: granted == true
            ? Colors.green
            : Theme.of(context).colorScheme.error,
      ),
      title: Text(granted == true
          ? 'Notification access granted'
          : 'Notification access needed'),
      subtitle: const Text('EDITH reads WhatsApp notifications to assist you.'),
      trailing: granted == true
          ? null
          : FilledButton(
              onPressed: () async {
                await ref
                    .read(whatsAppAssistProvider)
                    .openPermissionSettings();
              },
              child: const Text('Grant'),
            ),
    );
  }
}

class _MessageTile extends ConsumerStatefulWidget {
  const _MessageTile({required this.message});

  final WhatsAppMessage message;

  @override
  ConsumerState<_MessageTile> createState() => _MessageTileState();
}

class _MessageTileState extends ConsumerState<_MessageTile> {
  final _replyController = TextEditingController();
  bool _sending = false;
  String? _result;

  @override
  void dispose() {
    _replyController.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    setState(() {
      _sending = true;
      _result = null;
    });
    try {
      final ok = await ref.read(whatsAppAssistProvider).reply(
            notificationKey: widget.message.notificationKey,
            text: _replyController.text,
          );
      setState(() => _result = ok ? 'Sent' : 'Could not send');
    } catch (e) {
      setState(() => _result = 'Reply failed');
    } finally {
      if (mounted) {
        setState(() => _sending = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final msg = widget.message;
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(msg.sender, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 4),
          Text(msg.text),
          const SizedBox(height: 16),
          if (msg.canReply) ...[
            TextField(
              controller: _replyController,
              decoration: const InputDecoration(
                labelText: 'Reply',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                FilledButton(
                  onPressed: _sending ? null : _send,
                  child: const Text('Send reply'),
                ),
                if (_result != null) ...[
                  const SizedBox(width: 12),
                  Text(_result!),
                ],
              ],
            ),
          ] else
            const Text('This message has no direct-reply action.'),
        ],
      ),
    );
  }
}
