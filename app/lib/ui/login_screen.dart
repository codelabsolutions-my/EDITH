import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_service.dart';
import '../auth/auth_user.dart';
import '../auth/google_signin_service.dart';
import '../config.dart';
import '../providers.dart';
import 'chat_screen.dart';

/// Login surface. Primary path is "Sign in with Google"; a dev-login form
/// (email + display name) remains as a local-testing fallback.
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _emailController = TextEditingController();
  final _nameController = TextEditingController();
  bool _busy = false;
  bool _showDevLogin = false;
  String? _error;

  @override
  void dispose() {
    _emailController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  /// Common post-auth wiring: remember the user + token and open the chat.
  Future<void> _onSession(AuthUser user, String accessToken) async {
    ref.read(authUserProvider.notifier).set(user);
    ref.read(accessTokenProvider.notifier).set(accessToken);
    ref.read(chatControllerProvider.notifier).connect(accessToken);
    if (!mounted) {
      return;
    }
    await Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(builder: (_) => const ChatScreen()),
    );
  }

  Future<void> _signInWithGoogle() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await ref.read(googleSignInServiceProvider).signIn();
      final session =
          await ref.read(authServiceProvider).googleLogin(idToken: result.idToken);
      await _onSession(session.user, session.accessToken);
    } on GoogleSignInFailure catch (e) {
      setState(() => _error = e.message);
    } on AuthException catch (e) {
      setState(() => _error = 'Server rejected sign-in (${e.statusCode}).');
    } catch (_) {
      setState(() => _error = 'Could not reach the server.');
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _devLogin() async {
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
      await _onSession(session.user, session.accessToken);
    } on AuthException catch (e) {
      setState(() => _error = 'Login failed (${e.statusCode}).');
    } catch (_) {
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
      appBar: AppBar(title: const Text('EDITH')),
      body: Center(
        child: SingleChildScrollView(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 360),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Sign in to EDITH',
                    style: Theme.of(context).textTheme.headlineSmall,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 24),
                  FilledButton.icon(
                    onPressed: _busy ? null : _signInWithGoogle,
                    icon: const Icon(Icons.login),
                    label: const Text('Sign in with Google'),
                  ),
                  if (!AppConfig.hasGoogleWebClientId) ...[
                    const SizedBox(height: 8),
                    Text(
                      'Google client ID not configured — set '
                      'GOOGLE_WEB_CLIENT_ID via --dart-define.',
                      style: Theme.of(context).textTheme.bodySmall,
                      textAlign: TextAlign.center,
                    ),
                  ],
                  const SizedBox(height: 16),
                  if (_error != null) ...[
                    Text(
                      _error!,
                      style:
                          TextStyle(color: Theme.of(context).colorScheme.error),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 16),
                  ],
                  if (_busy)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 8),
                      child: Center(child: CircularProgressIndicator()),
                    ),
                  const Divider(height: 32),
                  TextButton(
                    onPressed: _busy
                        ? null
                        : () => setState(() => _showDevLogin = !_showDevLogin),
                    child: Text(
                      _showDevLogin ? 'Hide dev login' : 'Dev login (local testing)',
                    ),
                  ),
                  if (_showDevLogin) _buildDevLoginForm(context),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildDevLoginForm(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 8),
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
        const SizedBox(height: 16),
        OutlinedButton(
          onPressed: _busy ? null : _devLogin,
          child: const Text('Dev sign in'),
        ),
      ],
    );
  }
}
