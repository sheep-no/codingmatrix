// ignore_for_file: curly_braces_in_flow_control_structures
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/auth_controller.dart';
import '../application/workflow_controller.dart';
import '../infrastructure/workflow/workflow_client.dart';
import 'account_overlays.dart';
import 'dialog_controllers.dart';
import 'shell_scaffold.dart';

class WorkflowPage extends ConsumerStatefulWidget {
  const WorkflowPage({super.key});
  @override
  ConsumerState<WorkflowPage> createState() => _WorkflowPageState();
}

class _WorkflowPageState extends ConsumerState<WorkflowPage> {
  final input = TextEditingController();
  final timeout = TextEditingController(text: '1800');
  final form = GlobalKey<FormState>();
  final importController = TextEditingController();
  bool toolsBusy = false;
  // Bumped on account change so an in-flight history request does not open a
  // sheet over the next account.
  int _epoch = 0;
  WorkflowClient get client =>
      WorkflowClient(ref.read(authenticatedClientProvider));

  void _resetAccount() {
    _epoch++;
    closeAccountOverlays(context);
    input.clear();
    timeout.text = '1800';
  }

  @override
  void dispose() {
    input.dispose();
    timeout.dispose();
    importController.dispose();
    super.dispose();
  }

  Future<void> importWorkflow() async {
    importController.clear();
    final epoch = _epoch;
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => _ImportWorkflowDialog(
        controller: importController,
        onImport: (graph) => client.importWorkflow(graph),
      ),
    );
    if (result == null || !mounted || epoch != _epoch) return;
    setState(
      () => input.text =
          '${result['requirement'] ?? result['name'] ?? '已导入工作流'}',
    );
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(
      authControllerProvider.select((s) => s.session?.accessTokenRef),
      (_, __) => _resetAccount(),
    );
    ref.listen(apiBaseUrlProvider, (_, __) => _resetAccount());
    final state = ref.watch(workflowControllerProvider);
    final controller = ref.read(workflowControllerProvider.notifier);
    final snapshot = state.snapshot;
    return ShellScaffold(
      title: '工作流执行',
      actions: [
        IconButton(
          onPressed: toolsBusy
              ? null
              : () async {
                  final epoch = _epoch;
                  setState(() => toolsBusy = true);
                  try {
                    final items = await client.history();
                    if (!context.mounted || epoch != _epoch) return;
                    showModalBottomSheet<void>(
                      context: context,
                      builder: (_) => _WorkflowHistorySheet(
                        items: items,
                        onDelete: client.deleteHistory,
                      ),
                    );
                  } catch (e) {
                    if (mounted && epoch == _epoch)
                      ScaffoldMessenger.of(
                        context,
                      ).showSnackBar(SnackBar(content: Text('历史读取失败：$e')));
                  } finally {
                    if (mounted) setState(() => toolsBusy = false);
                  }
                },
          icon: const Icon(Icons.history),
        ),
      ],
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 960),
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const Text('输入任务后立即执行。离开页面会断开本地订阅，服务端任务状态以查询结果为准。'),
              Form(
                key: form,
                child: Column(
                  children: [
                    TextFormField(
                      key: const Key('workflowInput'),
                      controller: input,
                      minLines: 3,
                      maxLines: 6,
                      enabled: !state.active && !state.refreshing,
                      decoration: const InputDecoration(labelText: '任务描述'),
                      validator: (s) =>
                          s == null || s.trim().isEmpty ? '请输入任务描述' : null,
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: timeout,
                      enabled: !state.active && !state.refreshing,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(labelText: '超时（秒）'),
                      validator: (s) {
                        final n = int.tryParse(s ?? '');
                        return n == null || n < 60 || n > 3600
                            ? '请输入 60 至 3600'
                            : null;
                      },
                    ),
                  ],
                ),
              ),
              Wrap(
                spacing: 12,
                children: [
                  FilledButton(
                    key: const Key('workflowExecute'),
                    onPressed: state.active || state.refreshing
                        ? null
                        : () {
                            if (form.currentState!.validate()) {
                              controller.execute(
                                input.text,
                                timeout: int.parse(timeout.text),
                              );
                            }
                          },
                    child: const Text('执行工作流'),
                  ),
                  OutlinedButton(
                    onPressed: state.active || state.refreshing
                        ? null
                        : importWorkflow,
                    child: const Text('导入工作流'),
                  ),
                  if (state.active)
                    OutlinedButton(
                      onPressed: controller.disconnect,
                      child: const Text('断开本地连接'),
                    ),
                  if (snapshot.id != null)
                    OutlinedButton(
                      onPressed: state.active || state.refreshing
                          ? null
                          : controller.refresh,
                      child: Text(state.refreshing ? '查询中' : '查询状态'),
                    ),
                  if (snapshot.id != null)
                    OutlinedButton(
                      onPressed: toolsBusy
                          ? null
                          : () async {
                              final epoch = _epoch;
                              final messenger = ScaffoldMessenger.of(context);
                              setState(() => toolsBusy = true);
                              try {
                                final value = await client.exportWorkflow(
                                  snapshot.id!,
                                );
                                if (!context.mounted || epoch != _epoch) return;
                                showDialog<void>(
                                  context: context,
                                  builder: (dialogContext) => AlertDialog(
                                    title: const Text('工作流导出'),
                                    content: SelectableText(
                                      const JsonEncoder.withIndent(
                                        '  ',
                                      ).convert(value),
                                    ),
                                    actions: [
                                      TextButton(
                                        onPressed: () =>
                                            Navigator.pop(dialogContext),
                                        child: const Text('关闭'),
                                      ),
                                    ],
                                  ),
                                );
                              } catch (e) {
                                if (!context.mounted || epoch != _epoch) return;
                                messenger.showSnackBar(
                                  SnackBar(content: Text('导出失败：$e')),
                                );
                              } finally {
                                if (mounted) setState(() => toolsBusy = false);
                              }
                            },
                      child: const Text('导出工作流'),
                    ),
                ],
              ),
              if (state.active) const LinearProgressIndicator(),
              Text('状态：${snapshot.status}'),
              if (snapshot.id != null) SelectableText('工作流 ID：${snapshot.id}'),
              if (state.error != null)
                Text(
                  state.error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              if (snapshot.nodes.isNotEmpty)
                Text(
                  '任务图：${snapshot.nodes.where((n) => ['completed', 'failed', 'skipped'].contains(n.status)).length}/${snapshot.nodes.length} 已结束',
                ),
              for (final node in snapshot.nodes)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('${node.id} · ${node.type} · ${node.status}'),
                        Text(
                          '依赖：${node.dependencies.isEmpty ? '无' : node.dependencies.join(', ')}',
                        ),
                        ExpansionTile(
                          title: const Text('任务输入'),
                          children: [
                            SelectableText(
                              const JsonEncoder.withIndent(
                                '  ',
                              ).convert(node.params),
                            ),
                          ],
                        ),
                        if (node.result != null)
                          SelectableText(
                            const JsonEncoder.withIndent(
                              '  ',
                            ).convert(node.result),
                          ),
                        if (node.error != null) const Text('节点执行失败'),
                      ],
                    ),
                  ),
                ),
              if (snapshot.summary != null)
                SelectableText(
                  '结果摘要\n${const JsonEncoder.withIndent('  ').convert(snapshot.summary)}',
                ),
              ExpansionTile(
                title: Text('进度事件（${state.events.length}）'),
                children: state.events
                    .map((e) => ListTile(title: Text(e)))
                    .toList(),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _WorkflowHistorySheet extends StatefulWidget {
  const _WorkflowHistorySheet({required this.items, required this.onDelete});

  final List<Map<String, dynamic>> items;
  final Future<void> Function(String id) onDelete;

  @override
  State<_WorkflowHistorySheet> createState() => _WorkflowHistorySheetState();
}

class _WorkflowHistorySheetState extends State<_WorkflowHistorySheet> {
  bool deleting = false;

  Future<void> delete(String id) async {
    if (deleting || id.isEmpty) return;
    setState(() => deleting = true);
    try {
      await widget.onDelete(id);
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      if (!mounted) return;
      setState(() => deleting = false);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('删除失败：$e')));
    }
  }

  @override
  Widget build(BuildContext context) => ListView(
    children: [
      if (widget.items.isEmpty)
        const ListTile(dense: true, title: Text('暂无工作流历史')),
      for (final item in widget.items)
        ListTile(
          title: Text('${item['name'] ?? item['workflow_id'] ?? '工作流'}'),
          subtitle: Text('${item['status'] ?? ''}'),
          trailing: IconButton(
            tooltip: '删除历史',
            icon: const Icon(Icons.delete_outline),
            onPressed: deleting
                ? null
                : () => delete('${item['workflow_id'] ?? item['id'] ?? ''}'),
          ),
        ),
    ],
  );
}

/// 导入弹窗先校验 JSON，失败时保留弹窗和用户输入。
class _ImportWorkflowDialog extends StatefulWidget {
  const _ImportWorkflowDialog({
    required this.controller,
    required this.onImport,
  });

  final TextEditingController controller;
  final Future<Map<String, dynamic>> Function(Map<String, dynamic>) onImport;

  @override
  State<_ImportWorkflowDialog> createState() => _ImportWorkflowDialogState();
}

class _ImportWorkflowDialogState extends State<_ImportWorkflowDialog> {
  String? error;
  String? hint;
  bool busy = false;

  void _fail(String message, [String? detail]) {
    setState(() {
      error = message;
      hint = detail;
    });
  }

  Future<void> submit() async {
    if (busy) return;
    final raw = widget.controller.text.trim();
    if (raw.isEmpty) {
      _fail('请输入工作流 JSON');
      return;
    }
    late final Map<String, dynamic> graph;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) {
        _fail('工作流必须是 JSON 对象');
        return;
      }
      graph = Map<String, dynamic>.from(decoded);
    } on FormatException {
      _fail('JSON 格式错误', '请检查括号、引号和逗号');
      return;
    }

    setState(() {
      busy = true;
      error = null;
      hint = null;
    });
    try {
      final result = await widget.onImport(graph);
      if (mounted) Navigator.pop(context, result);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        busy = false;
        error = '导入失败';
        hint = '$e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('导入工作流 JSON'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: widget.controller,
                minLines: 8,
                maxLines: 14,
                enabled: !busy,
                decoration: const InputDecoration(hintText: '{"nodes":[]}'),
              ),
              if (error != null)
                DialogErrorNotice(message: error!, detail: hint),
              if (busy)
                const Padding(
                  padding: EdgeInsets.only(top: 12),
                  child: LinearProgressIndicator(),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: busy ? null : () => Navigator.pop(context),
          child: const Text('取消'),
        ),
        FilledButton(
          onPressed: busy ? null : submit,
          child: Text(busy ? '导入中…' : '导入'),
        ),
      ],
    );
  }
}
