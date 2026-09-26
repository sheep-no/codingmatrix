import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/auth_controller.dart';
import 'account_overlays.dart';
import 'dialog_controllers.dart';
import 'shell_scaffold.dart';

class AdminPage extends ConsumerStatefulWidget {
  const AdminPage({super.key});
  @override
  ConsumerState<AdminPage> createState() => _AdminPageState();
}

class _AdminPageState extends ConsumerState<AdminPage> {
  bool loading = false;
  String? error;
  Map<String, dynamic>? result;
  // Bumped on account change so a late response cannot write the previous
  // account's users or error into the new account's page state.
  int _epoch = 0;

  void _resetAccount() {
    _epoch++;
    closeAccountOverlays(context);
    setState(() {
      result = null;
      error = null;
      loading = false;
    });
  }

  // Every request shares the page-level guard so a second tap cannot start a
  // competing request, and so the buttons can be disabled while one runs.
  Future<void> run(String failure, Future<void> Function() action) async {
    if (loading || !mounted) return;
    final epoch = _epoch;
    setState(() {
      loading = true;
      error = null;
    });
    try {
      await action();
    } catch (e) {
      if (mounted && epoch == _epoch) setState(() => error = '$failure：$e');
    } finally {
      if (mounted && epoch == _epoch) setState(() => loading = false);
    }
  }

  // Reads the user list without taking the guard, so callers that already hold
  // it (create/update/delete) can refresh inside their own guarded block.
  Future<void> fetchUsers() async {
    final epoch = _epoch;
    final value = await ref
        .read(authenticatedClientProvider)
        .requestJson('/api/v2/Controller/users?page=1&page_size=50');
    if (mounted && epoch == _epoch) {
      setState(() => result = Map<String, dynamic>.from(value as Map));
    }
  }

  Future<void> createUser() async {
    final username = TextEditingController();
    final email = TextEditingController();
    final password = TextEditingController();
    final created = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('创建用户'),
        content: DialogControllers(
          controllers: [username, email, password],
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: username,
                  decoration: const InputDecoration(labelText: '用户名'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: email,
                  decoration: const InputDecoration(labelText: '邮箱'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: password,
                  obscureText: true,
                  decoration: const InputDecoration(labelText: '初始密码'),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('创建'),
          ),
        ],
      ),
    );
    if (created != true) return;
    final body = {
      'username': username.text.trim(),
      'email': email.text.trim(),
      'password': password.text,
    };
    await run('用户创建失败', () async {
      await ref
          .read(authenticatedClientProvider)
          .requestJson(
            '/api/v2/Controller/create_user',
            method: 'POST',
            body: body,
          );
      await fetchUsers();
    });
  }

  Future<void> removeUser(int id, String username) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('删除 $username？'),
        content: const Text('此操作会删除用户及其关联数据。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await run('用户删除失败', () async {
      await ref
          .read(authenticatedClientProvider)
          .requestJson('/api/v2/Controller/delete_user/$id', method: 'DELETE');
      await fetchUsers();
    });
  }

  Future<void> editUser(Map<String, dynamic> user) async {
    final username = TextEditingController(text: '${user['username'] ?? ''}');
    final email = TextEditingController(text: '${user['email'] ?? ''}');
    var permission = '${user['permission_level'] ?? 'normal'}';
    final saved = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('编辑用户'),
          content: DialogControllers(
            controllers: [username, email],
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextField(
                    controller: username,
                    decoration: const InputDecoration(labelText: '用户名'),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: email,
                    decoration: const InputDecoration(labelText: '邮箱'),
                  ),
                  const SizedBox(height: 12),
                  DropdownButton<String>(
                    value: permission,
                    items: const [
                      DropdownMenuItem(value: 'normal', child: Text('普通用户')),
                      DropdownMenuItem(value: 'admin', child: Text('管理员')),
                      DropdownMenuItem(
                        value: 'superadmin',
                        child: Text('超级管理员'),
                      ),
                    ],
                    onChanged: (value) =>
                        setDialogState(() => permission = value ?? 'normal'),
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('保存'),
            ),
          ],
        ),
      ),
    );
    final body = {
      'username': username.text.trim(),
      'email': email.text.trim(),
      'permission_level': permission,
    };
    if (saved != true || user['id'] is! int) return;
    await run('用户更新失败', () async {
      await ref
          .read(authenticatedClientProvider)
          .requestJson(
            '/api/v2/Controller/update_user/${user['id']}',
            method: 'PATCH',
            body: body,
          );
      await fetchUsers();
    });
  }

  Future<void> resetPassword(int id, String username) async {
    final password = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('重置 $username 的密码'),
        content: DialogControllers(
          controllers: [password],
          child: TextField(
            controller: password,
            obscureText: true,
            decoration: const InputDecoration(labelText: '新密码'),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('重置'),
          ),
        ],
      ),
    );
    final value = password.text;
    if (confirmed != true) return;
    final epoch = _epoch;
    await run('密码重置失败', () async {
      await ref
          .read(authenticatedClientProvider)
          .requestJson(
            '/api/v2/Controller/$id/reset-password',
            method: 'POST',
            body: {'new_password': value},
          );
      if (mounted && epoch == _epoch) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('密码已重置')));
      }
    });
  }

  Future<void> loadUsers() => run('用户列表读取失败', fetchUsers);

  Future<void> loadConfig() async {
    final epoch = _epoch;
    await run('配置读取失败', () async {
      final value = await ref
          .read(authenticatedClientProvider)
          .requestJson('/api/v2/admin/config');
      if (mounted && epoch == _epoch) {
        showDialog<void>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: const Text('系统配置'),
            content: SingleChildScrollView(child: SelectableText('$value')),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogContext),
                child: const Text('关闭'),
              ),
            ],
          ),
        );
      }
    });
  }

  Future<void> showEndpoint(String title, String path) async {
    final epoch = _epoch;
    await run('$title读取失败', () async {
      final value = await ref
          .read(authenticatedClientProvider)
          .requestJson(path);
      if (!mounted || epoch != _epoch) return;
      showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text(title),
          content: SingleChildScrollView(child: SelectableText('$value')),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('关闭'),
            ),
          ],
        ),
      );
    });
  }

  static const _logLevels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];

  Map<String, dynamic>? _asMap(Object? value) =>
      value is Map ? Map<String, dynamic>.from(value) : null;

  // Reads a config object first so the edit dialog can show current values.
  // Returns null when the read failed or the account changed mid-flight.
  Future<Map<String, dynamic>?> _fetchConfig(
    String failure,
    String path,
  ) async {
    final epoch = _epoch;
    Map<String, dynamic>? loaded;
    await run(failure, () async {
      final value = await ref
          .read(authenticatedClientProvider)
          .requestJson(path);
      if (mounted && epoch == _epoch) loaded = _asMap(value);
    });
    if (!mounted || epoch != _epoch) return null;
    return loaded;
  }

  Widget _numberField(
    String label,
    TextEditingController controller, {
    Key? key,
  }) {
    return Expanded(
      child: TextField(
        key: key,
        controller: controller,
        keyboardType: TextInputType.number,
        decoration: InputDecoration(labelText: label),
      ),
    );
  }

  static int? _positiveInt(TextEditingController controller) {
    final value = int.tryParse(controller.text.trim());
    return value != null && value > 0 ? value : null;
  }

  void _notify(String message) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> editSandboxConfig() async {
    final current = await _fetchConfig(
      '沙箱配置读取失败',
      '/api/v2/admin/sandbox-config',
    );
    if (!mounted || current == null) return;
    final epoch = _epoch;
    var enabled = current['enable_code_sandbox'] == true;
    final languages = current['sandbox_languages'];
    final languagesController = TextEditingController(
      text: languages is List ? languages.map((e) => '$e').join(',') : '',
    );
    final saved = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('沙箱配置'),
          content: DialogControllers(
            controllers: [languagesController],
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SwitchListTile(
                    key: const Key('sandboxEnabledSwitch'),
                    contentPadding: EdgeInsets.zero,
                    title: const Text('启用代码沙箱'),
                    value: enabled,
                    onChanged: (value) => setDialogState(() => enabled = value),
                  ),
                  TextField(
                    key: const Key('sandboxLanguagesField'),
                    controller: languagesController,
                    decoration: const InputDecoration(
                      labelText: '支持语言（逗号分隔）',
                      hintText: 'python,javascript',
                    ),
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('保存'),
            ),
          ],
        ),
      ),
    );
    final enabledValue = enabled;
    final languagesValue = languagesController.text.trim();
    if (saved != true || !mounted) return;
    await run('沙箱配置更新失败', () async {
      await ref
          .read(authenticatedClientProvider)
          .requestJson(
            '/api/v2/admin/sandbox-config',
            method: 'PUT',
            body: {
              'enable_code_sandbox': enabledValue,
              'sandbox_languages': languagesValue,
            },
          );
      if (mounted && epoch == _epoch) _notify('沙箱配置已更新，重启后生效');
    });
  }

  Future<void> editLogConfig() async {
    final current = await _fetchConfig(
      '日志配置读取失败',
      '/api/v2/Controller/admin/log-config',
    );
    if (!mounted || current == null) return;
    final epoch = _epoch;
    final reported = '${current['global_level'] ?? ''}'.toUpperCase();
    var level = _logLevels.contains(reported) ? reported : 'INFO';
    final saved = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('日志配置'),
          content: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('全局日志级别'),
              const SizedBox(width: 16),
              DropdownButton<String>(
                key: const Key('logLevelDropdown'),
                value: level,
                items: [
                  for (final item in _logLevels)
                    DropdownMenuItem(value: item, child: Text(item)),
                ],
                onChanged: (value) =>
                    setDialogState(() => level = value ?? level),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('保存'),
            ),
          ],
        ),
      ),
    );
    final levelValue = level;
    if (saved != true || !mounted) return;
    await run('日志级别更新失败', () async {
      await ref
          .read(authenticatedClientProvider)
          .requestJson(
            '/api/v2/Controller/admin/log-config/global-level?level=$levelValue',
            method: 'PUT',
          );
      if (mounted && epoch == _epoch) _notify('全局日志级别已更新为 $levelValue');
    });
  }

  Future<void> editRateLimit() async {
    final current = await _fetchConfig(
      '限流配置读取失败',
      '/api/v2/Controller/admin/rate-limit',
    );
    if (!mounted || current == null) return;
    final stored = _asMap(current['config']) ?? current;
    final epoch = _epoch;
    var enabled = stored['enabled'] == true;
    Map<String, dynamic> section(String key) => _asMap(stored[key]) ?? {};
    final global = section('global');
    final byIp = section('by_ip');
    final byUser = section('by_user');
    TextEditingController valueOf(Object? value) =>
        TextEditingController(text: '${value ?? ''}');
    final globalLimit = valueOf(global['limit']);
    final globalWindow = valueOf(global['window']);
    final ipLimit = valueOf(byIp['limit']);
    final ipWindow = valueOf(byIp['window']);
    final userLimit = valueOf(byUser['limit']);
    final userWindow = valueOf(byUser['window']);
    final saved = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('限流配置'),
          content: DialogControllers(
            controllers: [
              globalLimit,
              globalWindow,
              ipLimit,
              ipWindow,
              userLimit,
              userWindow,
            ],
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SwitchListTile(
                    key: const Key('rateLimitEnabledSwitch'),
                    contentPadding: EdgeInsets.zero,
                    title: const Text('启用限流'),
                    value: enabled,
                    onChanged: (value) => setDialogState(() => enabled = value),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      _numberField(
                        '全局 limit',
                        globalLimit,
                        key: const Key('rateLimitGlobalLimit'),
                      ),
                      const SizedBox(width: 12),
                      _numberField(
                        'window(秒)',
                        globalWindow,
                        key: const Key('rateLimitGlobalWindow'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      _numberField(
                        'IP limit',
                        ipLimit,
                        key: const Key('rateLimitIpLimit'),
                      ),
                      const SizedBox(width: 12),
                      _numberField(
                        'window(秒)',
                        ipWindow,
                        key: const Key('rateLimitIpWindow'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      _numberField(
                        '用户 limit',
                        userLimit,
                        key: const Key('rateLimitUserLimit'),
                      ),
                      const SizedBox(width: 12),
                      _numberField(
                        'window(秒)',
                        userWindow,
                        key: const Key('rateLimitUserWindow'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('保存'),
            ),
          ],
        ),
      ),
    );
    List<int?> pair(
      TextEditingController limit,
      TextEditingController window,
    ) => [_positiveInt(limit), _positiveInt(window)];
    final globalRule = pair(globalLimit, globalWindow);
    final ipRule = pair(ipLimit, ipWindow);
    final userRule = pair(userLimit, userWindow);
    if (saved != true || !mounted) return;
    if (globalRule.contains(null) ||
        ipRule.contains(null) ||
        userRule.contains(null)) {
      _notify('限流 limit 与 window 必须为正整数');
      return;
    }
    final enabledValue = enabled;
    await run('限流配置更新失败', () async {
      final api = ref.read(authenticatedClientProvider);
      await api.requestJson(
        '/api/v2/Controller/admin/rate-limit/enabled?enabled=$enabledValue',
        method: 'PUT',
      );
      for (final entry in {
        'global': globalRule,
        'ip': ipRule,
        'user': userRule,
      }.entries) {
        await api.requestJson(
          '/api/v2/Controller/admin/rate-limit/${entry.key}',
          method: 'PUT',
          body: {'limit': entry.value[0]!, 'window': entry.value[1]!},
        );
      }
      if (mounted && epoch == _epoch) _notify('限流配置已更新');
    });
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(
      authControllerProvider.select((s) => s.session?.accessTokenRef),
      (_, __) => _resetAccount(),
    );
    ref.listen(apiBaseUrlProvider, (_, __) => _resetAccount());
    return ShellScaffold(
      title: '管理员后台',
      actions: [
        IconButton(
          onPressed: loading ? null : loadUsers,
          icon: const Icon(Icons.refresh),
        ),
      ],
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton.icon(
                onPressed: loading ? null : loadUsers,
                icon: const Icon(Icons.people),
                label: const Text('用户管理'),
              ),
              OutlinedButton.icon(
                onPressed: loading ? null : createUser,
                icon: const Icon(Icons.person_add),
                label: const Text('创建用户'),
              ),
              OutlinedButton.icon(
                onPressed: loading ? null : loadConfig,
                icon: const Icon(Icons.settings),
                label: const Text('系统配置'),
              ),
              OutlinedButton.icon(
                onPressed: loading
                    ? null
                    : () => showEndpoint(
                        '系统统计',
                        '/api/v2/Controller/admin/stats',
                      ),
                icon: const Icon(Icons.monitor_heart),
                label: const Text('系统统计'),
              ),
              OutlinedButton.icon(
                onPressed: loading ? null : editSandboxConfig,
                icon: const Icon(Icons.security),
                label: const Text('沙箱配置'),
              ),
              OutlinedButton.icon(
                onPressed: loading
                    ? null
                    : () => showEndpoint('MCP 服务', '/api/v2/mcp/servers'),
                icon: const Icon(Icons.extension),
                label: const Text('MCP 服务'),
              ),
              OutlinedButton.icon(
                onPressed: loading
                    ? null
                    : () => showEndpoint(
                        '内存状态',
                        '/api/v2/Controller/admin/memory',
                      ),
                icon: const Icon(Icons.memory),
                label: const Text('内存状态'),
              ),
              OutlinedButton.icon(
                onPressed: loading ? null : editRateLimit,
                icon: const Icon(Icons.speed),
                label: const Text('限流配置'),
              ),
              OutlinedButton.icon(
                onPressed: loading ? null : editLogConfig,
                icon: const Icon(Icons.article_outlined),
                label: const Text('日志配置'),
              ),
            ],
          ),
          if (loading) const LinearProgressIndicator(),
          if (error != null)
            Text(
              error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          if (result != null) ...[
            Text('用户总数：${result!['total'] ?? 0}'),
            for (final user in (result!['users'] as List? ?? const []))
              Card(
                child: ListTile(
                  title: Text('${user['username'] ?? ''}'),
                  subtitle: Text(
                    '${user['email'] ?? ''}\n权限：${user['permission_level'] ?? 'normal'}',
                  ),
                  isThreeLine: true,
                  trailing: user['id'] is int
                      ? Wrap(
                          children: [
                            IconButton(
                              tooltip: '编辑',
                              onPressed: loading ? null : () => editUser(user),
                              icon: const Icon(Icons.edit),
                            ),
                            IconButton(
                              tooltip: '重置密码',
                              onPressed: loading
                                  ? null
                                  : () => resetPassword(
                                      user['id'] as int,
                                      '${user['username']}',
                                    ),
                              icon: const Icon(Icons.password),
                            ),
                            IconButton(
                              tooltip: '删除',
                              onPressed: loading
                                  ? null
                                  : () => removeUser(
                                      user['id'] as int,
                                      '${user['username']}',
                                    ),
                              icon: const Icon(Icons.delete_outline),
                            ),
                          ],
                        )
                      : null,
                ),
              ),
          ],
        ],
      ),
    );
  }
}
