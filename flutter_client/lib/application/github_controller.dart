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
    this.repos = const [],
    this.branches = const [],
    this.commits = const [],
    this.selectedRepo,
    this.verifyMessage,
  });
  final GithubBinding? binding;
  final bool loading;
  final String? error;
  final bool saved;
  final List<GithubRepo> repos;
  final List<GithubBranch> branches;
  final List<GithubCommit> commits;
  final String? selectedRepo;
  final String? verifyMessage;
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

  Future<bool> verify() async {
    if (!mounted || state.loading) return false;
    final op = ++_operation;
    final previous = state;
    state = GithubState(binding: previous.binding, loading: true);
    try {
      final result = await client.verify();
      if (!_current(op)) return false;
      final verified = result['verified'] == true;
      state = GithubState(
        binding: previous.binding,
        verifyMessage: result['message'] as String? ?? (verified ? 'GitHub 凭据有效' : '验证未通过'),
        error: verified ? null : (result['message'] as String? ?? '用户名与 Token 不匹配'),
      );
      return verified;
    } catch (_) {
      if (!_current(op)) return false;
      state = GithubState(binding: previous.binding, error: 'GitHub 验证失败，请确认已保存凭据');
      return false;
    }
  }

  Future<void> loadRepos() async {
    if (!mounted || state.loading) return;
    final op = ++_operation;
    final previous = state;
    state = GithubState(
      binding: previous.binding,
      loading: true,
      verifyMessage: previous.verifyMessage,
    );
    try {
      final repos = await client.listRepos();
      if (_current(op)) {
        state = GithubState(
          binding: previous.binding,
          repos: repos,
          verifyMessage: previous.verifyMessage,
        );
      }
    } catch (_) {
      if (_current(op)) {
        state = GithubState(
          binding: previous.binding,
          verifyMessage: previous.verifyMessage,
          error: '仓库列表读取失败，请先验证凭据',
        );
      }
    }
  }

  Future<void> loadBranches(GithubRepo repo) async {
    if (!mounted || state.loading) return;
    final op = ++_operation;
    final previous = state;
    state = GithubState(
      binding: previous.binding,
      loading: true,
      repos: previous.repos,
      selectedRepo: repo.fullName,
      verifyMessage: previous.verifyMessage,
    );
    try {
      final branches = await client.listBranches(repo.owner, repo.name);
      if (_current(op)) {
        state = GithubState(
          binding: previous.binding,
          repos: previous.repos,
          branches: branches,
          selectedRepo: repo.fullName,
          verifyMessage: previous.verifyMessage,
        );
      }
    } catch (_) {
      if (_current(op)) {
        state = GithubState(
          binding: previous.binding,
          repos: previous.repos,
          selectedRepo: repo.fullName,
          verifyMessage: previous.verifyMessage,
          error: '分支列表读取失败',
        );
      }
    }
  }

  Future<void> loadCommits(GithubRepo repo, {String? sha}) async {
    if (!mounted || state.loading) return;
    final op = ++_operation;
    final previous = state;
    state = GithubState(
      binding: previous.binding,
      loading: true,
      repos: previous.repos,
      branches: previous.branches,
      selectedRepo: repo.fullName,
      verifyMessage: previous.verifyMessage,
    );
    try {
      final commits = await client.listCommits(repo.owner, repo.name, sha: sha);
      if (_current(op)) {
        state = GithubState(
          binding: previous.binding,
          repos: previous.repos,
          branches: previous.branches,
          commits: commits,
          selectedRepo: repo.fullName,
          verifyMessage: previous.verifyMessage,
        );
      }
    } catch (_) {
      if (_current(op)) {
        state = GithubState(
          binding: previous.binding,
          repos: previous.repos,
          branches: previous.branches,
          selectedRepo: repo.fullName,
          verifyMessage: previous.verifyMessage,
          error: '提交列表读取失败',
        );
      }
    }
  }

  Future<void> loadCommitsForSelection(String sha) async {
    GithubRepo? selected;
    for (final repo in state.repos) {
      if (repo.fullName == state.selectedRepo) selected = repo;
    }
    if (selected == null) return;
    await loadCommits(selected, sha: sha);
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
