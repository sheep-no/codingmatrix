import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/auth_controller.dart';
import '../application/github_controller.dart';

class GithubSettingsPage extends ConsumerStatefulWidget {
  const GithubSettingsPage({super.key});
  @override
  ConsumerState<GithubSettingsPage> createState() => _GithubSettingsPageState();
}

class _GithubSettingsPageState extends ConsumerState<GithubSettingsPage> {
  final username = TextEditingController();
  final token = TextEditingController();
  bool enabled = false;

  @override
  void initState() {
    super.initState();
    _scheduleLoad();
  }

  void _scheduleLoad() {
    Future.microtask(() {
      if (mounted) ref.read(githubControllerProvider.notifier).load();
    });
  }

  void _resetAccount() {
    username.clear();
    token.clear();
    setState(() => enabled = false);
    _scheduleLoad();
  }

  @override
  void dispose() {
    username.dispose();
    token.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(
      authControllerProvider.select((s) => s.session?.accessTokenRef),
      (_, __) => _resetAccount(),
    );
    ref.listen(apiBaseUrlProvider, (_, __) => _resetAccount());
    ref.listen(githubControllerProvider, (previous, next) {
      if (next.binding != null &&
          !next.loading &&
          next.error == null &&
          (previous?.loading == true)) {
        username.text = next.binding!.username;
        token.clear();
        setState(() => enabled = next.binding!.useGithub);
      }
    });
    final state = ref.watch(githubControllerProvider);
    final controller = ref.read(githubControllerProvider.notifier);
    return Scaffold(
      appBar: AppBar(title: const Text('GitHub 设置')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (state.loading) const LinearProgressIndicator(),
          TextField(
            key: const Key('githubUsername'),
            controller: username,
            enabled: !state.loading,
            decoration: const InputDecoration(labelText: 'GitHub 用户名'),
          ),
          const SizedBox(height: 12),
          TextField(
            key: const Key('githubToken'),
            controller: token,
            enabled: !state.loading,
            obscureText: true,
            autocorrect: false,
            enableSuggestions: false,
            decoration: InputDecoration(
              labelText: 'Personal Access Token',
              helperText: state.binding?.configured == true
                  ? '留空保留同名账号的 Token；填写新 Token 可更新'
                  : '令牌仅用于本次提交',
              helperMaxLines: 3,
            ),
          ),
          SwitchListTile(
            title: const Text('启用 GitHub 保存'),
            value: enabled,
            onChanged: state.loading
                ? null
                : (value) => setState(() => enabled = value),
          ),
          FilledButton(
            key: const Key('githubSave'),
            onPressed: state.loading
                ? null
                : () {
                    controller.save(
                      username: username.text.trim(),
                      token: token.text.trim(),
                      useGithub: enabled,
                    );
                  },
            child: const Text('提交配置'),
          ),
          const SizedBox(height: 16),
          OutlinedButton(
            onPressed: state.loading ? null : controller.load,
            child: const Text('重新读取配置'),
          ),
          const SizedBox(height: 8),
          OutlinedButton(
            key: const Key('githubVerify'),
            onPressed: state.loading ? null : controller.verify,
            child: const Text('验证凭据'),
          ),
          const SizedBox(height: 8),
          OutlinedButton(
            key: const Key('githubListRepos'),
            onPressed: state.loading ? null : controller.loadRepos,
            child: const Text('读取仓库列表'),
          ),
          Text(
            state.saved
                ? '配置已保存'
                : '配置状态：${state.binding == null
                      ? '尚未读取'
                      : state.binding!.persisted
                      ? '已持久化'
                      : '尚未配置'}',
          ),
          if (state.binding != null) ...[
            Text('GitHub 保存：${state.binding!.useGithub ? '已启用' : '已停用'}'),
            Text(
              '凭据状态：${switch (state.binding!.credentialState) {
                'stored' => '已加密保存',
                'missing' => '尚未提供 Token',
                'unreadable' => '凭据无法读取，请重新填写 Token',
                _ => '未知，请重新读取配置',
              }}',
            ),
            Text('远端验证：${state.binding!.verified ? '已验证' : '尚未验证'}'),
          ],
          if (state.verifyMessage != null) Text(state.verifyMessage!),
          for (final repo in state.repos)
            ListTile(
              title: Text(repo.fullName),
              subtitle: Text(
                repo.private
                    ? '私有 · ${repo.defaultBranch}'
                    : '公开 · ${repo.defaultBranch}',
              ),
              onTap: state.loading ? null : () => controller.loadBranches(repo),
            ),
          if (state.branches.isNotEmpty)
            Wrap(
              spacing: 8,
              children: [
                for (final branch in state.branches)
                  ActionChip(
                    label: Text(branch.name),
                    onPressed: state.loading
                        ? null
                        : () => controller.loadCommitsForSelection(branch.name),
                  ),
              ],
            ),
          for (final commit in state.commits)
            ListTile(
              dense: true,
              title: Text(commit.message),
              subtitle: Text(
                '${commit.sha.length >= 7 ? commit.sha.substring(0, 7) : commit.sha}  ${commit.author}',
              ),
            ),
          if (state.error != null)
            Text(
              state.error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          const SizedBox(height: 8),
          const Text('配置按当前登录账号保存。验证凭据后可读取仓库、分支和最近提交。'),
        ],
      ),
    );
  }
}
