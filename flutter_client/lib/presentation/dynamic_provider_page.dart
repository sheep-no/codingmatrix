import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/auth_controller.dart';
import '../infrastructure/provider/dynamic_provider_client.dart';
import 'account_overlays.dart';

class DynamicProviderPage extends ConsumerStatefulWidget {
  const DynamicProviderPage({super.key});
  @override
  ConsumerState<DynamicProviderPage> createState() =>
      _DynamicProviderPageState();
}

class _DynamicProviderPageState extends ConsumerState<DynamicProviderPage> {
  final name = TextEditingController(),
      url = TextEditingController(),
      key = TextEditingController();
  String protocol = 'openai';
  bool loading = false;
  String? error;
  List<DynamicProvider> items = const [];
  // Bumped on account change so a late response cannot write the previous
  // account's providers or error into the new account's page state.
  int _epoch = 0;
  DynamicProviderClient get client =>
      DynamicProviderClient(ref.read(authenticatedClientProvider));
  @override
  void initState() {
    super.initState();
    Future.microtask(load);
  }

  @override
  void dispose() {
    name.dispose();
    url.dispose();
    key.dispose();
    super.dispose();
  }

  void _resetAccount() {
    _epoch++;
    closeAccountOverlays(context);
    name.clear();
    url.clear();
    key.clear();
    setState(() {
      protocol = 'openai';
      items = const [];
      error = null;
      loading = false;
    });
    load();
  }

  Future<void> load() async {
    final epoch = _epoch;
    try {
      final result = await client.list();
      if (!mounted || epoch != _epoch) return;
      setState(() => items = result);
    } catch (e) {
      if (!mounted || epoch != _epoch) return;
      setState(() => error = '$e');
    }
  }

  Future<void> run(Future<void> Function() action) async {
    if (loading || !mounted) return;
    final epoch = _epoch;
    setState(() {
      loading = true;
      error = null;
    });
    try {
      await action();
      if (epoch != _epoch) return;
      await load();
    } catch (e) {
      if (mounted && epoch == _epoch) setState(() => error = '$e');
    } finally {
      if (mounted && epoch == _epoch) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(
      authControllerProvider.select((s) => s.session?.accessTokenRef),
      (_, __) => _resetAccount(),
    );
    ref.listen(apiBaseUrlProvider, (_, __) => _resetAccount());
    return Scaffold(
      appBar: AppBar(title: const Text('动态 Provider')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: name,
            decoration: const InputDecoration(labelText: '名称'),
          ),
          TextField(
            controller: url,
            decoration: const InputDecoration(labelText: 'Base URL'),
          ),
          DropdownButtonFormField<String>(
            // Keyed by the current protocol so resetting the draft on account
            // change actually moves the visible selection back to the default.
            key: ValueKey(protocol),
            initialValue: protocol,
            items: const [
              DropdownMenuItem(value: 'openai', child: Text('OpenAI 协议')),
              DropdownMenuItem(value: 'anthropic', child: Text('Anthropic 协议')),
            ],
            onChanged: loading ? null : (v) => setState(() => protocol = v!),
            decoration: const InputDecoration(labelText: '协议'),
          ),
          TextField(
            controller: key,
            obscureText: true,
            decoration: const InputDecoration(labelText: 'API Key'),
          ),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: loading
                ? null
                : () => run(() async {
                    final epoch = _epoch;
                    await client.add(
                      name: name.text.trim(),
                      baseUrl: url.text.trim(),
                      protocol: protocol,
                      apiKey: key.text.trim(),
                    );
                    if (!mounted || epoch != _epoch) return;
                    name.clear();
                    url.clear();
                    key.clear();
                  }),
            child: const Text('添加供应商'),
          ),
          if (error != null)
            Text(
              error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          const Divider(),
          for (final item in items)
            Card(
              child: ListTile(
                title: Text(item.name),
                subtitle: Text(
                  '${item.baseUrl}\n${item.protocol} · ${item.models.length} 个模型${item.syncError.isEmpty ? '' : '\n同步失败: ${item.syncError}'}',
                ),
                isThreeLine: true,
                trailing: PopupMenuButton<String>(
                  enabled: !loading,
                  onSelected: (action) => run(() async {
                    if (action == 'toggle') await client.toggle(item.id);
                    if (action == 'sync') await client.sync(item.id);
                    if (action == 'test') await client.test(item.id);
                    if (action == 'delete') await client.delete(item.id);
                  }),
                  itemBuilder: (_) => [
                    PopupMenuItem(
                      value: 'toggle',
                      child: Text(item.enabled ? '停用' : '启用'),
                    ),
                    const PopupMenuItem(value: 'sync', child: Text('同步模型')),
                    const PopupMenuItem(value: 'test', child: Text('测试连接')),
                    const PopupMenuItem(value: 'delete', child: Text('删除')),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
