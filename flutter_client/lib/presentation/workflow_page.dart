import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/auth_controller.dart';
import '../application/workflow_controller.dart';

class WorkflowPage extends ConsumerStatefulWidget {
  const WorkflowPage({super.key});
  @override
  ConsumerState<WorkflowPage> createState() => _WorkflowPageState();
}

class _WorkflowPageState extends ConsumerState<WorkflowPage> {
  final input = TextEditingController();
  final timeout = TextEditingController(text: '1800');
  final form = GlobalKey<FormState>();
  @override
  void dispose() {
    input.dispose();
    timeout.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(
      authControllerProvider.select((s) => s.session?.accessTokenRef),
      (_, __) => input.clear(),
    );
    ref.listen(apiBaseUrlProvider, (_, __) => input.clear());
    final state = ref.watch(workflowControllerProvider);
    final controller = ref.read(workflowControllerProvider.notifier);
    final snapshot = state.snapshot;
    return Scaffold(
      appBar: AppBar(title: const Text('工作流执行')),
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
