import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../domain/models/github_binding.dart';
import '../infrastructure/github/github_client.dart';
import 'auth_controller.dart';

class GithubState {
  const GithubState({
    this.binding,
    this.loading = false,
    this.error,
    this.saved = false,
  });
  final GithubBinding? binding;
  final bool loading;
  final String? error;
  final bool saved;
}

class GithubController extends StateNotifier<GithubState> {
  GithubController(this.client) : super(const GithubState());
  final GithubClient client;
  int _operation = 0;
  bool _current(int op) => mounted && op == _operation;

  Future<void> load() async {
    if (!mounted || state.loading) return;
    final op = ++_operation;
    state = const GithubState(loading: true);
    try {
      final binding = await client.load();
      if (_current(op)) state = GithubState(binding: binding);
    } catch (_) {
      if (_current(op)) state = const GithubState(error: 'GitHub 配置加载失败，请重试');
    }
  }

  Future<bool> save({
    required String username,
    required String token,
    required bool useGithub,
  }) async {
    if (!mounted || state.loading) return false;
    username = username.trim();
    token = token.trim();
    final previousBinding = state.binding;
    if ((username.isNotEmpty &&
            !RegExp(
              r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$',
            ).hasMatch(username)) ||
        token.length > 4096 ||
        RegExp(r'\s').hasMatch(token) ||
        (token.isNotEmpty && username.isEmpty)) {
      state = GithubState(
        binding: previousBinding,
        error: '请填写有效的 GitHub 用户名和 Token',
      );
      return false;
    }
    if (previousBinding != null &&
        previousBinding.credentialState != 'missing' &&
        previousBinding.persisted &&
        username.toLowerCase() != previousBinding.username.toLowerCase() &&
        token.isEmpty) {
      state = GithubState(
        binding: previousBinding,
        error: '变更 GitHub 用户名时请提供新 Token',
      );
      return false;
    }
    if (useGithub &&
        (username.trim().isEmpty ||
            (token.trim().isEmpty &&
                (state.binding?.configured != true ||
                    username.trim().toLowerCase() !=
                        state.binding!.username.toLowerCase())))) {
      state = GithubState(
        binding: state.binding,
        error: '启用前请填写用户名和 Token；已有同名配置可保留 Token',
      );
      return false;
    }
    final op = ++_operation;
    final previous = state.binding;
    state = GithubState(binding: state.binding, loading: true);
    try {
      final binding = await client.save(
        username: username,
        token: token,
        useGithub: useGithub,
      );
      if (!_current(op)) return false;
      state = GithubState(binding: binding, saved: true);
      return true;
    } catch (_) {
      if (!_current(op)) return false;
      state = GithubState(
        binding: previous,
        error: 'GitHub 配置提交失败或结果未知，请重新读取配置确认状态',
      );
      return false;
    }
  }
}

final githubControllerProvider =
    StateNotifierProvider.autoDispose<GithubController, GithubState>((ref) {
      ref.watch(apiBaseUrlProvider);
      ref.watch(
        authControllerProvider.select((s) => s.session?.accessTokenRef),
      );
      return GithubController(
        GithubClient(ref.watch(authenticatedClientProvider)),
      );
    });
