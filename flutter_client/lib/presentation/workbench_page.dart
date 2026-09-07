import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../application/auth_controller.dart';
import '../application/workbench_controller.dart';
import '../domain/models/unified_models.dart';
import '../infrastructure/sse/sse_parser.dart';

class WorkbenchPage extends ConsumerStatefulWidget {
  const WorkbenchPage({super.key});

  @override
  ConsumerState<WorkbenchPage> createState() => _WorkbenchPageState();
}

class _WorkbenchPageState extends ConsumerState<WorkbenchPage> {
  final _requirementController = TextEditingController();

  @override
  void dispose() {
    _requirementController.dispose();
    super.dispose();
  }

  Future<void> _startGeneration(AuthState auth) async {
    final requirement = _requirementController.text.trim();
    final tokenRef = auth.session?.accessTokenRef;
    if (requirement.isEmpty || tokenRef == null) {
      return;
    }
    await ref
        .read(workbenchControllerProvider.notifier)
        .startGeneration(accessTokenRef: tokenRef, requirement: requirement);
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    final workbench = ref.watch(workbenchControllerProvider);
    final session = auth.session;
    final task = workbench.task;

    return Scaffold(
      appBar: AppBar(
        title: const Text('工作台'),
        actions: [
          if (session != null)
            Center(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Tooltip(
                  message: session.username,
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 160),
                    child: Text(
                      session.username,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ),
              ),
            ),
          TextButton(
            key: const Key('logoutButton'),
            onPressed: () async {
              await ref
                  .read(workbenchControllerProvider.notifier)
                  .stopGeneration();
              if (mounted) {
                ref.read(authControllerProvider.notifier).logout();
              }
            },
            child: const Text('退出'),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: LayoutBuilder(
          builder: (context, constraints) {
            final compact = constraints.maxWidth < 720;
            final overview = _OverviewCard(workbench: workbench, task: task);
            final events = _EventsCard(events: workbench.events);
            final isRunning = task?.status == 'running';
            final heading = Text(
              workbench.agent?.name ?? 'CodingMatrix Agent',
              style: Theme.of(context).textTheme.headlineSmall,
            );

            if (compact) {
              return SingleChildScrollView(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    heading,
                    const SizedBox(height: 16),
                    _PromptCard(
                      controller: _requirementController,
                      isRunning: isRunning,
                      onStart: () => _startGeneration(auth),
                      onStop: () => ref
                          .read(workbenchControllerProvider.notifier)
                          .stopGeneration(),
                    ),
                    const SizedBox(height: 16),
                    overview,
                    const SizedBox(height: 16),
                    SizedBox(height: 320, child: events),
                  ],
                ),
              );
            }

            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                heading,
                const SizedBox(height: 16),
                _PromptCard(
                  controller: _requirementController,
                  isRunning: isRunning,
                  onStart: () => _startGeneration(auth),
                  onStop: () => ref
                      .read(workbenchControllerProvider.notifier)
                      .stopGeneration(),
                ),
                const SizedBox(height: 16),
                Expanded(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      SizedBox(width: 300, child: overview),
                      const SizedBox(width: 16),
                      Expanded(child: events),
                    ],
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _PromptCard extends StatelessWidget {
  const _PromptCard({
    required this.controller,
    required this.isRunning,
    required this.onStart,
    required this.onStop,
  });

  final TextEditingController controller;
  final bool isRunning;
  final VoidCallback onStart;
  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: TextField(
                key: const Key('requirementField'),
                controller: controller,
                minLines: 1,
                maxLines: 3,
                decoration: const InputDecoration(
                  labelText: '告诉 Agent 你要完成什么',
                  hintText: '例如：创建一个带登录页的 Flutter 应用',
                  prefixIcon: Icon(Icons.edit_note_outlined),
                ),
              ),
            ),
            const SizedBox(width: 12),
            isRunning
                ? OutlinedButton.icon(
                    key: const Key('stopGenerationButton'),
                    onPressed: onStop,
                    icon: const Icon(Icons.stop_circle_outlined),
                    label: const Text('停止'),
                  )
                : FilledButton.icon(
                    key: const Key('startGenerationButton'),
                    onPressed: onStart,
                    icon: const Icon(Icons.play_arrow_rounded),
                    label: const Text('开始'),
                  ),
          ],
        ),
      ),
    );
  }
}

class _OverviewCard extends StatelessWidget {
  const _OverviewCard({required this.workbench, required this.task});

  final WorkbenchState workbench;
  final Task? task;

  @override
  Widget build(BuildContext context) {
    final progress = ((task?.progress ?? 0) / 100).clamp(0.0, 1.0).toDouble();
    final status = task?.status ?? workbench.agent?.status ?? 'idle';
    final statusColor = switch (status) {
      'success' => Colors.greenAccent,
      'failed' => Colors.redAccent,
      'running' => Colors.amberAccent,
      _ => Theme.of(context).colorScheme.primary,
    };
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('任务概览', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 18),
            _InfoRow(label: '会话', value: workbench.session?.id ?? '未绑定'),
            _InfoRow(label: '任务', value: task?.taskId ?? '无'),
            _InfoRow(label: '阶段', value: task?.stage ?? '等待任务'),
            const SizedBox(height: 18),
            Row(
              children: [
                Text('状态', style: Theme.of(context).textTheme.bodySmall),
                const Spacer(),
                Chip(
                  label: Text(status),
                  side: BorderSide.none,
                  backgroundColor: statusColor.withValues(alpha: 0.16),
                  labelStyle: TextStyle(color: statusColor),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('进度', style: Theme.of(context).textTheme.bodySmall),
                Text('${task?.progress ?? 0}%'),
              ],
            ),
            const SizedBox(height: 8),
            LinearProgressIndicator(value: progress, minHeight: 8),
          ],
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 48,
            child: Text(label, style: Theme.of(context).textTheme.bodySmall),
          ),
          Expanded(
            child: Text(value, maxLines: 2, overflow: TextOverflow.ellipsis),
          ),
        ],
      ),
    );
  }
}

class _EventsCard extends StatelessWidget {
  const _EventsCard({required this.events});

  final List<SseEvent> events;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('实时事件', style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                Text(
                  '${events.length} 条',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
            const SizedBox(height: 12),
            Expanded(
              child: events.isEmpty
                  ? Center(
                      child: Text(
                        '等待 Agent 事件流',
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                    )
                  : ListView.separated(
                      itemCount: events.length,
                      separatorBuilder: (_, __) => const Divider(height: 16),
                      itemBuilder: (context, index) {
                        final event = events[index];
                        return SelectableText(
                          '${event.type}: ${event.raw}',
                          style: const TextStyle(
                            fontFamily: 'monospace',
                            fontSize: 12,
                          ),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }
}
