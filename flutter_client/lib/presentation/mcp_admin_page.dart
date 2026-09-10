import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../application/auth_controller.dart';
import '../infrastructure/mcp/mcp_admin_client.dart';

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

  Future<void> load() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final value = await ref.read(mcpAdminClientProvider).listServers();
      if (mounted) setState(() => servers = value);
    } catch (e) {
      if (mounted) setState(() => error = 'MCP 服务读取失败：$e');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> add() async {
    final name = nameController.text.trim();
    if (name.isEmpty) return;
    try {
      await ref
          .read(mcpAdminClientProvider)
          .addServer(
            name: name,
            transport: transport,
            command: commandController.text.trim(),
            url: urlController.text.trim(),
          );
      nameController.clear();
      commandController.clear();
      urlController.clear();
      await load();
    } catch (e) {
      if (mounted) setState(() => error = 'MCP 服务添加失败：$e');
    }
  }

  Future<void> testServer(String name) async {
    try {
      final result = await ref.read(mcpAdminClientProvider).test(name);
      if (!mounted) return;
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
    } catch (e) {
      if (mounted) setState(() => error = '连接测试失败：$e');
    }
  }

  Future<void> toggleServer(String name) async {
    try {
      await ref.read(mcpAdminClientProvider).toggle(name);
      await load();
    } catch (e) {
      if (mounted) setState(() => error = 'MCP 服务状态更新失败：$e');
    }
  }

  Future<void> editServer(Map<String, dynamic> server) async {
    final command = TextEditingController(text: '${server['command'] ?? ''}');
    final url = TextEditingController(text: '${server['url'] ?? ''}');
    var enabled = server['enabled'] == true;
    final save = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text('编辑 ${server['name']}'),
          content: Column(
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
    if (save != true) return;
    final body = <String, dynamic>{
      'enabled': enabled,
      if (server['transport'] == 'stdio') 'command': command.text.trim(),
      if (server['transport'] == 'http') 'url': url.text.trim(),
    };
    command.dispose();
    url.dispose();
    try {
      await ref
          .read(mcpAdminClientProvider)
          .updateServer('${server['name']}', body);
      await load();
    } catch (e) {
      if (mounted) setState(() => error = 'MCP 服务更新失败：$e');
    }
  }

  Future<void> removeServer(String name) async {
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
    try {
      await ref.read(mcpAdminClientProvider).deleteServer(name);
      await load();
    } catch (e) {
      if (mounted) setState(() => error = 'MCP 服务删除失败：$e');
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('MCP 服务管理'),
      actions: [
        IconButton(
          onPressed: loading ? null : load,
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
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
                server['enabled'] == true ? Icons.toggle_on : Icons.toggle_off,
              ),
              trailing: Wrap(
                spacing: 4,
                children: [
                  IconButton(
                    tooltip: '编辑',
                    onPressed: () => editServer(server),
                    icon: const Icon(Icons.edit),
                  ),
                  IconButton(
                    tooltip: '连接测试',
                    onPressed: () => testServer('${server['name']}'),
                    icon: const Icon(Icons.network_check),
                  ),
                  IconButton(
                    tooltip: '启停',
                    onPressed: () => toggleServer('${server['name']}'),
                    icon: const Icon(Icons.power_settings_new),
                  ),
                  IconButton(
                    tooltip: '删除',
                    onPressed: () => removeServer('${server['name']}'),
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
