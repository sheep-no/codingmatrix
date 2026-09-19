import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../application/auth_controller.dart';
import '../application/generation_flags_controller.dart';
import '../application/provider_key_controller.dart';
import '../application/workbench_controller.dart';
import '../domain/models/generation_flags.dart';
import '../domain/models/unified_models.dart';
import '../infrastructure/sse/sse_parser.dart';
import 'account_overlays.dart';
import 'agent_decision_page.dart';
import 'project_files_page.dart';

/// The Agent workbench body: prompt input, generation switches, task overview
/// and the live event stream. Rendered by the workbench shell as the `agent`
/// capability.
class AgentHomeView extends ConsumerStatefulWidget {
  const AgentHomeView({super.key});

  @override
  ConsumerState<AgentHomeView> createState() => _AgentHomeViewState();
}

class _AgentHomeViewState extends ConsumerState<AgentHomeView> {
  final _requirementController = TextEditingController();

  @override
  void dispose() {
    _requirementController.dispose();
    super.dispose();
  }

  void _resetAccount() {
    closeAccountOverlays(context);
    _requirementController.clear();
  }

  Future<void> _startGeneration(AuthState auth) async {
    final requirement = _requirementController.text.trim();
    final tokenRef = auth.session?.accessTokenRef;
    if (requirement.isEmpty || tokenRef == null) {
      return;
    }
    // Take the switches now: a mid-generation change must not alter this run.
    final flags = ref.read(generationFlagsControllerProvider);
    try {
      await ref
          .read(workbenchControllerProvider.notifier)
          .startGeneration(
            accessTokenRef: tokenRef,
            requirement: requirement,
            providerKey: ref.read(providerKeyControllerProvider).selected,
            flags: flags,
          );
    } catch (_) {
      // The controller already recorded the disconnect it must report; the
      // fire-and-forget button flow must not leak an unhandled async error.
    }
  }

  Future<void> _confirmStop() async {
    final taskId = ref.read(workbenchControllerProvider).task?.taskId;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('停止并清理项目文件？'),
        content: const Text('此操作会停止服务端任务并删除已生成的项目文件。退出登录仅断开本地连接。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('继续任务'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('停止并清理'),
          ),
        ],
      ),
    );
    if (mounted &&
        confirmed == true &&
        ref.read(workbenchControllerProvider).task?.taskId == taskId) {
      await ref.read(workbenchControllerProvider.notifier).stopGeneration();
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(
      authControllerProvider.select((s) => s.session?.accessTokenRef),
      (_, __) => _resetAccount(),
    );
    ref.listen(apiBaseUrlProvider, (_, __) => _resetAccount());
    final auth = ref.watch(authControllerProvider);
    final workbench = ref.watch(workbenchControllerProvider);
    final task = workbench.task;

    return Padding(
      padding: const EdgeInsets.all(16),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final compact = constraints.maxWidth < 720;
          final overview = _OverviewCard(workbench: workbench, task: task);
          final events = _EventsCard(events: workbench.events);
          final isRunning = workbench.active;
          final actions = Wrap(
            spacing: 12,
            children: [
              if (workbench.decisions.isNotEmpty)
                FilledButton(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => const AgentDecisionPage(),
                    ),
                  ),
                  child: const Text('处理架构决策'),
                ),
              if (workbench.projectPath != null)
                OutlinedButton(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) =>
                          ProjectFilesPage(project: workbench.projectPath!),
                    ),
                  ),
                  child: const Text('查看项目文件'),
                ),
              if (workbench.actionError != null) Text(workbench.actionError!),
              if (task?.status == 'disconnected')
                const Text('连接已断开，服务端任务状态待确认。可在「会话历史」中选择该会话恢复连接。'),
            ],
          );
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
                    onStop: _confirmStop,
                  ),
                  const SizedBox(height: 16),
                  actions,
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
                onStop: _confirmStop,
              ),
              const SizedBox(height: 16),
              actions,
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
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
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
            const SizedBox(height: 8),
            const _GenerationFlagsPanel(),
          ],
        ),
      ),
    );
  }
}

class _GenerationFlagsPanel extends ConsumerWidget {
  const _GenerationFlagsPanel();

  static const _labels = <GenerationFlag, String>{
    GenerationFlag.review: '代码审查',
    GenerationFlag.validation: '结果校验',
    GenerationFlag.errorRecovery: '错误恢复',
    GenerationFlag.memory: '记忆',
    GenerationFlag.skills: 'Skills 技能',
    GenerationFlag.specFirst: '先写规格',
    GenerationFlag.dependencyGraph: '依赖图',
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final flags = ref.watch(generationFlagsControllerProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '生成选项 · 已启用 ${flags.enabledCount}/7',
          key: const Key('generationFlagsPanel'),
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final entry in _labels.entries)
              FilterChip(
                key: Key('generationFlag_${entry.key.name}'),
                label: Text(entry.value),
                selected: switch (entry.key) {
                  GenerationFlag.review => flags.enableReview,
                  GenerationFlag.validation => flags.enableValidation,
                  GenerationFlag.errorRecovery => flags.enableErrorRecovery,
                  GenerationFlag.memory => flags.enableMemory,
                  GenerationFlag.skills => flags.enableSkills,
                  GenerationFlag.specFirst => flags.specFirst,
                  GenerationFlag.dependencyGraph => flags.dependencyGraph,
                },
                onSelected: (_) => ref
                    .read(generationFlagsControllerProvider.notifier)
                    .toggle(entry.key),
              ),
          ],
        ),
      ],
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
      child: SingleChildScrollView(
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
