import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../application/auth_controller.dart';
import '../infrastructure/mcp/mcp_admin_client.dart';
import 'account_overlays.dart';
import 'shell_scaffold.dart';

final mcpAdminClientProvider = Provider<McpAdminClient>((ref) {
  return McpAdminClient(ref.watch(authenticatedClientProvider));
});

class McpAdminPage extends ConsumerStatefulWidget {
  const McpAdminPage({super.key});
  @override
  ConsumerState<McpAdminPage> createState() => _McpAdminPageState();
}

class _McpAdminPageState extends ConsumerState<McpAdminPage> {
  final nameController = TextEditingController();
  final commandController = TextEditingController();
  final urlController = TextEditingController();
  List<Map<String, dynamic>> servers = [];
  String transport = 'stdio';
  String? error;
  bool loading = false;
  // Bumped on account change so a late response cannot write the previous
  // account's servers or error into the new account's page state.
  int _epoch = 0;

  @override
  void initState() {
    super.initState();
    load();
  }

  @override
  void dispose() {
    nameController.dispose();
    commandController.dispose();
    urlController.dispose();
    super.dispose();
  }

  void _resetAccount() {
    _epoch++;
    closeAccountOverlays(context);
    nameController.clear();
    commandController.clear();
    urlController.clear();
    setState(() {
      servers = [];
      transport = 'stdio';
      error = null;
      loading = false;
    });
    load();
  }

  Future<void> load() async {
    if (!mounted) return;
    final epoch = _epoch;
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final value = await ref.read(mcpAdminClientProvider).listServers();
      if (!mounted || epoch != _epoch) return;
      setState(() => servers = value);
    } catch (e) {
      if (!mounted || epoch != _epoch) return;
      setState(() => error = 'MCP 服务读取失败：$e');
    } finally {
      if (mounted && epoch == _epoch) setState(() => loading = false);
    }
  }

  // Writes share the page-level guard so a second tap cannot start a competing
  // request while the first one is still in flight.
  Future<void> mutate(String failure, Future<void> Function() action) async {
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

  Future<void> add() async {
    final name = nameController.text.trim();
    if (name.isEmpty) return;
    final epoch = _epoch;
    await mutate('MCP 服务添加失败', () async {
      await ref
          .read(mcpAdminClientProvider)
          .addServer(
            name: name,
            transport: transport,
            command: commandController.text.trim(),
            url: urlController.text.trim(),
          );
      if (!mounted || epoch != _epoch) return;
      nameController.clear();
      commandController.clear();
      urlController.clear();
      await load();
    });
  }

  Future<void> testServer(String name) async {
    final epoch = _epoch;
    await mutate('连接测试失败', () async {
      final result = await ref.read(mcpAdminClientProvider).test(name);
      if (!mounted || epoch != _epoch) return;
      showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text('$name 连接测试'),
          content: SelectableText('$result'),
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

  Future<void> toggleServer(String name) async {
    await mutate('MCP 服务状态更新失败', () async {
      await ref.read(mcpAdminClientProvider).toggle(name);
      await load();
    });
  }

  Future<void> editServer(Map<String, dynamic> server) async {
    if (loading) return;
    final command = TextEditingController(text: '${server['command'] ?? ''}');
    final url = TextEditingController(text: '${server['url'] ?? ''}');
    var enabled = server['enabled'] == true;
    final save = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text('编辑 ${server['name']}'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                SwitchListTile(
                  title: const Text('启用'),
                  value: enabled,
                  onChanged: (value) => setDialogState(() => enabled = value),
                ),
                if (server['transport'] == 'stdio')
                  TextField(
                    controller: command,
                    decoration: const InputDecoration(labelText: '命令路径'),
                  ),
                if (server['transport'] == 'http')
                  TextField(
                    controller: url,
                    decoration: const InputDecoration(labelText: '服务 URL'),
                  ),
              ],
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
    // Read the fields and release the controllers before the early return so a
    // cancelled edit does not leak them.
    final commandText = command.text.trim();
    final urlText = url.text.trim();
    command.dispose();
    url.dispose();
    if (save != true) return;
    final body = <String, dynamic>{
      'enabled': enabled,
      if (server['transport'] == 'stdio') 'command': commandText,
      if (server['transport'] == 'http') 'url': urlText,
    };
    await mutate('MCP 服务更新失败', () async {
      await ref
          .read(mcpAdminClientProvider)
          .updateServer('${server['name']}', body);
      await load();
    });
  }

  Future<void> removeServer(String name) async {
    if (loading) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('删除 $name？'),
        content: const Text('删除后需要重新添加服务配置。'),
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
    await mutate('MCP 服务删除失败', () async {
      await ref.read(mcpAdminClientProvider).deleteServer(name);
      await load();
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
      title: 'MCP 服务管理',
      actions: [
        IconButton(
          onPressed: loading ? null : load,
          icon: const Icon(Icons.refresh),
        ),
      ],
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    '添加 MCP 服务',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  TextField(
                    controller: nameController,
                    decoration: const InputDecoration(labelText: '名称'),
                  ),
                  DropdownButton<String>(
                    value: transport,
                    items: const [
                      DropdownMenuItem(value: 'stdio', child: Text('stdio')),
                      DropdownMenuItem(value: 'http', child: Text('http')),
                    ],
                    onChanged: (value) =>
                        setState(() => transport = value ?? 'stdio'),
                  ),
                  if (transport == 'stdio')
                    TextField(
                      controller: commandController,
                      decoration: const InputDecoration(labelText: '命令路径'),
                    ),
                  if (transport == 'http')
                    TextField(
                      controller: urlController,
                      decoration: const InputDecoration(labelText: '服务 URL'),
                    ),
                  const SizedBox(height: 8),
                  FilledButton.icon(
                    onPressed: loading ? null : add,
                    icon: const Icon(Icons.add),
                    label: const Text('添加'),
                  ),
                ],
              ),
            ),
          ),
          if (loading) const LinearProgressIndicator(),
          if (error != null)
            Text(
              error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          for (final server in servers)
            Card(
              child: ListTile(
                title: Text('${server['name'] ?? ''}'),
                subtitle: Text(
                  '${server['transport'] ?? ''}  ${server['description'] ?? ''}',
                ),
                leading: Icon(
                  server['enabled'] == true
                      ? Icons.toggle_on
                      : Icons.toggle_off,
                ),
                trailing: Wrap(
                  spacing: 4,
                  children: [
                    IconButton(
                      tooltip: '编辑',
                      onPressed: loading ? null : () => editServer(server),
                      icon: const Icon(Icons.edit),
                    ),
                    IconButton(
                      tooltip: '连接测试',
                      onPressed: loading
                          ? null
                          : () => testServer('${server['name']}'),
                      icon: const Icon(Icons.network_check),
                    ),
                    IconButton(
                      tooltip: '启停',
                      onPressed: loading
                          ? null
                          : () => toggleServer('${server['name']}'),
                      icon: const Icon(Icons.power_settings_new),
                    ),
                    IconButton(
                      tooltip: '删除',
                      onPressed: loading
                          ? null
                          : () => removeServer('${server['name']}'),
                      icon: const Icon(Icons.delete_outline),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
