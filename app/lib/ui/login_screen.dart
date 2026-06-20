import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_service.dart';
import '../providers.dart';
import 'chat_screen.dart';

/// Dev-login surface: email + display name -> `POST /auth/dev-login`.
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _emailController = TextEditingController();
  final _nameController = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _emailController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    final email = _emailController.text.trim();
    final name = _nameController.text.trim();
    if (email.isEmpty || name.isEmpty) {
      setState(() => _error = 'Enter both an email and a display name.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final session = await ref.read(authServiceProvider).devLogin(
            email: email,
            displayName: name,
          );
      ref.read(authUserProvider.notifier).set(session.user);
      ref.read(chatControllerProvider.notifier).connect(session.accessToken);
      if (!mounted) {
        return;
      }
      await Navigator.of(context).pushReplacement(
        MaterialPageRoute<void>(builder: (_) => const ChatScreen()),
      );
    } on AuthException catch (e) {
      setState(() => _error = 'Login failed (${e.statusCode}).');
    } catch (e) {
      setState(() => _error = 'Could not reach the server.');
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('EDITH — Dev Login')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 360),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextField(
                  controller: _emailController,
                  keyboardType: TextInputType.emailAddress,
                  decoration: const InputDecoration(
                    labelText: 'Email',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _nameController,
                  decoration: const InputDecoration(
                    labelText: 'Display name',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 24),
                if (_error != null) ...[
                  Text(
                    _error!,
                    style: TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                  const SizedBox(height: 16),
                ],
                FilledButton(
                  onPressed: _busy ? null : _login,
                  child: _busy
                      ? const SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Sign in'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
