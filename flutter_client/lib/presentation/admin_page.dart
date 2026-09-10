import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/auth_controller.dart';

class AdminPage extends ConsumerStatefulWidget {
  const AdminPage({super.key});
  @override
  ConsumerState<AdminPage> createState() => _AdminPageState();
}

class _AdminPageState extends ConsumerState<AdminPage> {
  bool loading = false;
  String? error;
  Map<String, dynamic>? result;

  Future<void> createUser() async {
    final username = TextEditingController();
    final email = TextEditingController();
    final password = TextEditingController();
    final created = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('创建用户'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: username,
              decoration: const InputDecoration(labelText: '用户名'),
            ),
            TextField(
              controller: email,
              decoration: const InputDecoration(labelText: '邮箱'),
            ),
            TextField(
              controller: password,
              obscureText: true,
              decoration: const InputDecoration(labelText: '初始密码'),
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
            child: const Text('创建'),
          ),
        ],
      ),
    );
    if (created != true) {
      username.dispose();
      email.dispose();
      password.dispose();
      return;
    }
    try {
      await ref
          .read(authenticatedClientProvider)
          .requestJson(
            '/api/v2/Controller/create_user',
            method: 'POST',
            body: {
              'username': username.text.trim(),
              'email': email.text.trim(),
              'password': password.text,
            },
          );
      await loadUsers();
    } catch (e) {
      if (mounted) setState(() => error = '用户创建失败：$e');
    }
    username.dispose();
    email.dispose();
    password.dispose();
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
    try {
      await ref
          .read(authenticatedClientProvider)
          .requestJson('/api/v2/Controller/delete_user/$id', method: 'DELETE');
      await loadUsers();
    } catch (e) {
      if (mounted) setState(() => error = '用户删除失败：$e');
    }
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
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: username,
                decoration: const InputDecoration(labelText: '用户名'),
              ),
              TextField(
                controller: email,
                decoration: const InputDecoration(labelText: '邮箱'),
              ),
              DropdownButton<String>(
                value: permission,
                items: const [
                  DropdownMenuItem(value: 'normal', child: Text('普通用户')),
                  DropdownMenuItem(value: 'admin', child: Text('管理员')),
                  DropdownMenuItem(value: 'superadmin', child: Text('超级管理员')),
                ],
                onChanged: (value) =>
                    setDialogState(() => permission = value ?? 'normal'),
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
    final body = {
      'username': username.text.trim(),
      'email': email.text.trim(),
      'permission_level': permission,
    };
    username.dispose();
    email.dispose();
    if (saved != true || user['id'] is! int) return;
    try {
      await ref
          .read(authenticatedClientProvider)
          .requestJson(
            '/api/v2/Controller/update_user/${user['id']}',
            method: 'PATCH',
            body: body,
          );
      await loadUsers();
    } catch (e) {
      if (mounted) setState(() => error = '用户更新失败：$e');
    }
  }

  Future<void> resetPassword(int id, String username) async {
    final password = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('重置 $username 的密码'),
        content: TextField(
          controller: password,
          obscureText: true,
          decoration: const InputDecoration(labelText: '新密码'),
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
    password.dispose();
    if (confirmed != true) return;
    try {
      await ref
          .read(authenticatedClientProvider)
          .requestJson(
            '/api/v2/Controller/$id/reset-password',
            method: 'POST',
            body: {'new_password': value},
          );
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('密码已重置')));
      }
    } catch (e) {
      if (mounted) setState(() => error = '密码重置失败：$e');
    }
  }

  Future<void> loadUsers() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final value = await ref
          .read(authenticatedClientProvider)
          .requestJson('/api/v2/Controller/users?page=1&page_size=50');
      if (mounted) {
        setState(() => result = Map<String, dynamic>.from(value as Map));
      }
    } catch (e) {
      if (mounted) setState(() => error = '用户列表读取失败：$e');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> loadConfig() async {
    try {
      final value = await ref
          .read(authenticatedClientProvider)
          .requestJson('/api/v2/admin/config');
      if (mounted) {
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
    } catch (e) {
      if (mounted) setState(() => error = '配置读取失败：$e');
    }
  }

  Future<void> showEndpoint(String title, String path) async {
    try {
      final value = await ref
          .read(authenticatedClientProvider)
          .requestJson(path);
      if (!mounted) return;
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
    } catch (e) {
      if (mounted) setState(() => error = '$title读取失败：$e');
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('管理员后台'),
      actions: [
        IconButton(
          onPressed: loading ? null : loadUsers,
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
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
              onPressed: loadConfig,
              icon: const Icon(Icons.settings),
              label: const Text('系统配置'),
            ),
            OutlinedButton.icon(
              onPressed: () =>
                  showEndpoint('系统统计', '/api/v2/Controller/admin/stats'),
              icon: const Icon(Icons.monitor_heart),
              label: const Text('系统统计'),
            ),
            OutlinedButton.icon(
              onPressed: () =>
                  showEndpoint('沙箱配置', '/api/v2/admin/sandbox-config'),
              icon: const Icon(Icons.security),
              label: const Text('沙箱配置'),
            ),
            OutlinedButton.icon(
              onPressed: () => showEndpoint('MCP 服务', '/api/v2/mcp/servers'),
              icon: const Icon(Icons.extension),
              label: const Text('MCP 服务'),
            ),
            OutlinedButton.icon(
              onPressed: () =>
                  showEndpoint('内存状态', '/api/v2/Controller/admin/memory'),
              icon: const Icon(Icons.memory),
              label: const Text('内存状态'),
            ),
            OutlinedButton.icon(
              onPressed: () =>
                  showEndpoint('限流配置', '/api/v2/Controller/admin/rate-limit'),
              icon: const Icon(Icons.speed),
              label: const Text('限流配置'),
            ),
            OutlinedButton.icon(
              onPressed: () =>
                  showEndpoint('日志配置', '/api/v2/Controller/admin/log-config'),
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
                            onPressed: () => editUser(user),
                            icon: const Icon(Icons.edit),
                          ),
                          IconButton(
                            tooltip: '重置密码',
                            onPressed: () => resetPassword(
                              user['id'] as int,
                              '${user['username']}',
                            ),
                            icon: const Icon(Icons.password),
                          ),
                          IconButton(
                            tooltip: '删除',
                            onPressed: () => removeUser(
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
