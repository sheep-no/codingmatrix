import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../application/provider_key_controller.dart';
import '../infrastructure/provider/provider_key_client.dart';

class ProviderSettingsPage extends ConsumerStatefulWidget {
  const ProviderSettingsPage({super.key});
  @override
  ConsumerState<ProviderSettingsPage> createState() =>
      _ProviderSettingsPageState();
}

class _ProviderSettingsPageState extends ConsumerState<ProviderSettingsPage> {
  final keyController = TextEditingController();
  String provider = supportedProviders.first;
  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      if (mounted) ref.read(providerKeyControllerProvider.notifier).load();
    });
  }

  @override
  void dispose() {
    keyController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(providerKeyControllerProvider);
    final controller = ref.read(providerKeyControllerProvider.notifier);
    return Scaffold(
      appBar: AppBar(title: const Text('Provider 设置')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          DropdownButtonFormField<String>(
            initialValue: provider,
            items: supportedProviders
                .map((p) => DropdownMenuItem(value: p, child: Text(p)))
                .toList(),
            onChanged: state.loading
                ? null
                : (v) => setState(() => provider = v!),
            decoration: const InputDecoration(labelText: 'Provider'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: keyController,
            enabled: !state.loading,
            obscureText: true,
            autocorrect: false,
            enableSuggestions: false,
            decoration: const InputDecoration(
              labelText: 'API Key',
              helperText: '有效期 24 小时；原始 Key 仅用于加密提交',
            ),
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: state.loading
                ? null
                : () async {
                    final value = keyController.text.trim();
                    if (value.isEmpty) return;
                    final ok = await controller.add(
                      key: value,
                      provider: provider,
                    );
                    if (!mounted) return;
                    if (ok) keyController.clear();
                  },
            child: const Text('添加 Provider Key'),
          ),
          TextButton(
            onPressed: state.loading ? null : controller.load,
            child: const Text('刷新列表'),
          ),
          if (state.error != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(
                state.error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          const SizedBox(height: 20),
          ...state.items.map(
            (item) => Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${item.provider} · 授权 ${state.items.indexOf(item) + 1}',
                    ),
                    Text('${item.status} · ${item.enabled ? '已启用' : '已停用'}'),
                    Text('有效期：${item.expiresAt?.toLocal().toString() ?? '长期'}'),
                    Wrap(
                      spacing: 8,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        TextButton(
                          onPressed: state.loading || !item.isUsable
                              ? null
                              : () => controller.select(item),
                          child: Text(
                            state.selected?.token == item.token
                                ? '当前生成授权'
                                : '用于生成',
                          ),
                        ),
                        TextButton(
                          onPressed: state.loading
                              ? null
                              : () async {
                                  await controller.test(item);
                                  if (!context.mounted) return;
                                  if (ref
                                          .read(providerKeyControllerProvider)
                                          .error ==
                                      null) {
                                    ScaffoldMessenger.of(context).showSnackBar(
                                      const SnackBar(content: Text('连接测试通过')),
                                    );
                                  }
                                },
                          child: const Text('测试连接'),
                        ),
                        Switch(
                          value: item.enabled,
                          onChanged: state.loading
                              ? null
                              : (_) => controller.toggle(item),
                        ),
                        IconButton(
                          tooltip: '删除授权',
                          icon: const Icon(Icons.delete_outline),
                          onPressed: state.loading
                              ? null
                              : () async {
                                  final confirmed = await showDialog<bool>(
                                    context: context,
                                    builder: (dialogContext) => AlertDialog(
                                      title: const Text('删除 Provider Key？'),
                                      content: const Text(
                                        '删除后 Agent 将无法继续使用此授权。',
                                      ),
                                      actions: [
                                        TextButton(
                                          onPressed: () => Navigator.pop(
                                            dialogContext,
                                            false,
                                          ),
                                          child: const Text('取消'),
                                        ),
                                        FilledButton(
                                          onPressed: () => Navigator.pop(
                                            dialogContext,
                                            true,
                                          ),
                                          child: const Text('确认'),
                                        ),
                                      ],
                                    ),
                                  );
                                  if (!mounted) return;
                                  if (confirmed == true) {
                                    await controller.remove(item);
                                  }
                                },
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
