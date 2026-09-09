import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../application/auth_controller.dart';

class LoginPage extends ConsumerStatefulWidget {
  const LoginPage({super.key});

  @override
  ConsumerState<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends ConsumerState<LoginPage> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _baseUrlController = TextEditingController(
    text: 'http://127.0.0.1:8080',
  );
  bool _obscurePassword = true;

  @override
  void initState() {
    super.initState();
    _baseUrlController.text = ref.read(cloudAuthClientProvider).baseUrl;
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _baseUrlController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) {
      return;
    }
    await ref
        .read(authControllerProvider.notifier)
        .login(
          email: _emailController.text.trim(),
          password: _passwordController.text,
          serviceUrl: _baseUrlController.text.trim(),
        );
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(28),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Container(
                          width: 56,
                          height: 56,
                          decoration: BoxDecoration(
                            color: Theme.of(
                              context,
                            ).colorScheme.primaryContainer,
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: Icon(
                            Icons.auto_awesome,
                            color: Theme.of(
                              context,
                            ).colorScheme.onPrimaryContainer,
                            size: 28,
                          ),
                        ),
                        const SizedBox(height: 20),
                        Text(
                          'CodingMatrix Agent',
                          style: Theme.of(context).textTheme.headlineSmall,
                        ),
                        const SizedBox(height: 8),
                        Text(
                          '登录云端工作台',
                          style: Theme.of(context).textTheme.bodyMedium,
                        ),
                        const SizedBox(height: 24),
                        TextFormField(
                          key: const Key('baseUrlField'),
                          controller: _baseUrlController,
                          decoration: const InputDecoration(
                            prefixIcon: Icon(Icons.link),
                            labelText: 'API Base URL',
                            helperText: '云端服务地址',
                          ),
                          validator: (value) =>
                              value == null || value.trim().isEmpty
                              ? '请输入 API 地址'
                              : null,
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          key: const Key('emailField'),
                          controller: _emailController,
                          keyboardType: TextInputType.emailAddress,
                          decoration: const InputDecoration(
                            prefixIcon: Icon(Icons.mail_outline),
                            labelText: '邮箱',
                          ),
                          validator: (value) =>
                              value == null || !value.contains('@')
                              ? '请输入有效邮箱'
                              : null,
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          key: const Key('passwordField'),
                          controller: _passwordController,
                          obscureText: _obscurePassword,
                          decoration: InputDecoration(
                            prefixIcon: const Icon(Icons.lock_outline),
                            labelText: '密码',
                            suffixIcon: IconButton(
                              tooltip: _obscurePassword ? '显示密码' : '隐藏密码',
                              onPressed: () => setState(() {
                                _obscurePassword = !_obscurePassword;
                              }),
                              icon: Icon(
                                _obscurePassword
                                    ? Icons.visibility_outlined
                                    : Icons.visibility_off_outlined,
                              ),
                            ),
                          ),
                          onFieldSubmitted: (_) => _submit(),
                          validator: (value) =>
                              value == null || value.isEmpty ? '请输入密码' : null,
                        ),
                        if (auth.errorMessage != null) ...[
                          const SizedBox(height: 12),
                          Container(
                            key: const Key('loginError'),
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: Theme.of(
                                context,
                              ).colorScheme.errorContainer,
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Text(
                              auth.errorMessage!,
                              style: TextStyle(
                                color: Theme.of(
                                  context,
                                ).colorScheme.onErrorContainer,
                              ),
                            ),
                          ),
                        ],
                        const SizedBox(height: 20),
                        FilledButton(
                          key: const Key('loginButton'),
                          onPressed: auth.isLoading ? null : _submit,
                          child: auth.isLoading
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Text('登录'),
                        ),
                        TextButton(
                          onPressed: auth.isLoading
                              ? null
                              : () => ref
                                    .read(authControllerProvider.notifier)
                                    .logout(),
                          child: const Text('清除本地会话'),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
