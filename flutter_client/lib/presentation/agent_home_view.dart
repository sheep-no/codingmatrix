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
import 'model_service_hint.dart';
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
  final _projectNameController = TextEditingController();

  @override
  void dispose() {
    _requirementController.dispose();
    _projectNameController.dispose();
    super.dispose();
  }

  void _resetAccount() {
    closeAccountOverlays(context);
    _requirementController.clear();
    _projectNameController.clear();
  }

  Future<void> _startGeneration(AuthState auth) async {
    final requirement = _requirementController.text.trim();
    final tokenRef = auth.session?.accessTokenRef;
    if (requirement.isEmpty || tokenRef == null) {
      return;
    }
    // Take the switches now: a mid-generation change must not alter this run.
    final flags = ref.read(generationFlagsControllerProvider);
    // A finished run left a project behind, so this requirement modifies it
    // instead of starting from scratch. A cancelled run was cleaned up, so it
    // must start over even though it still reports a project path.
    final workbench = ref.read(workbenchControllerProvider);
    final projectPath = workbench.task?.status == 'success'
        ? workbench.projectPath
        : null;
    final projectName = _projectNameController.text.trim();
    try {
      await ref
          .read(workbenchControllerProvider.notifier)
          .startGeneration(
            accessTokenRef: tokenRef,
            requirement: requirement,
            projectName: projectName.isEmpty ? null : projectName,
            providerKey: ref.read(providerKeyControllerProvider).selected,
            incremental: projectPath != null,
            projectPath: projectPath,
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
          final compact =
              constraints.maxWidth < 720 || constraints.maxHeight < 600;
          final overview = _OverviewCard(workbench: workbench, task: task);
          final events = _EventsCard(events: workbench.events, task: task);
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
              if (workbench.actionError != null)
                ModelServiceHint(error: workbench.actionError!),
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
                    projectNameController: _projectNameController,
                    task: task,
                    isRunning: isRunning,
                    onStart: () => _startGeneration(auth),
                    onStop: _confirmStop,
                  ),
                  const SizedBox(height: 16),
                  actions,
                  const SizedBox(height: 16),
                  SizedBox(height: 320, child: events),
                  const SizedBox(height: 16),
                  overview,
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
                projectNameController: _projectNameController,
                task: task,
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
    required this.projectNameController,
    required this.task,
    required this.isRunning,
    required this.onStart,
    required this.onStop,
  });

  final TextEditingController controller;
  final TextEditingController projectNameController;
  final Task? task;
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
                  child: Semantics(
                    label: '任务需求',
                    hint: '输入要交给 Agent 完成的任务',
                    textField: true,
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
            _RunStatusStrip(task: task),
            const SizedBox(height: 8),
            Semantics(
              label: '项目名称',
              hint: '可选，输入英文项目名，留空自动生成',
              textField: true,
              child: TextField(
                key: const Key('projectNameField'),
                controller: projectNameController,
                maxLength: 50,
                decoration: const InputDecoration(
                  labelText: '项目名称（可选，留空自动生成）',
                  hintText: '例如：my_flutter_app',
                  prefixIcon: Icon(Icons.folder_outlined),
                  counterText: '',
                ),
              ),
            ),
            const SizedBox(height: 8),
            const _GenerationFlagsPanel(),
          ],
        ),
      ),
    );
  }
}

/// The event log renders every frame, but `file` and `file_diff` payloads embed
/// whole file bodies. Summarize those and cap everything else so a large
/// project cannot make one list item lay out an entire source file.
String _eventLabel(SseEvent event) {
  final data = event.data;
  String? text;
  if (event.type == 'progress') {
    final stage = data?['step'] ?? data?['phase'] ?? data?['stage'];
    final percent = data?['percentage'] ?? data?['progress'];
    text = [
      '进度',
      if (stage is String && stage.isNotEmpty) stage,
      if (percent is num) '${percent.toInt()}%',
    ].join(' · ');
  } else if (event.type == 'log') {
    final message = data?['message'] ?? data?['value'];
    if (message is String && message.isNotEmpty) text = message;
  } else if (event.type == 'error') {
    final message = data?['error'] ?? data?['message'];
    if (message is String && message.isNotEmpty) text = '失败：$message';
  } else if (event.type == 'done') {
    final files = data?['total_files_created'];
    text = files is num ? '完成 · 已生成 ${files.toInt()} 个文件' : '完成';
  } else if (event.type == 'pipeline_mode') {
    final mode = data?['mode'] ?? data?['pipeline_mode'];
    if (mode is String && mode.isNotEmpty) text = '生成模式 · $mode';
  } else if (data != null &&
      (event.type == 'file' || event.type == 'file_diff')) {
    final path = data['path'];
    if (path is String && path.isNotEmpty) {
      final operation = data['operation'];
      final size = data['file_size_human'];
      text = [
        event.type,
        path,
        if (operation is String && operation.isNotEmpty) operation,
        if (size is String && size.isNotEmpty) size,
      ].join(' · ');
    }
  }
  text ??= '${event.type}: ${event.raw}';
  const limit = 2000;
  if (text.length <= limit) return text;
  return '${text.substring(0, limit)}…（已截断 ${text.length - limit} 字符）';
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
    return Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        key: const Key('generationFlagsPanel'),
        initiallyExpanded: false,
        tilePadding: EdgeInsets.zero,
        childrenPadding: const EdgeInsets.only(bottom: 4),
        title: Text(
          '生成选项 · 已启用 ${flags.enabledCount}/7',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        subtitle: const Text('点按展开或收起 7 项生成能力'),
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: Wrap(
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
          ),
        ],
      ),
    );
  }
}

String _statusLabel(String status) {
  return switch (status) {
    'running' => '运行中',
    'awaitingDecision' => '等待决策',
    'stopping' => '停止中',
    'disconnected' => '连接断开',
    'success' => '已完成',
    'failed' => '失败',
    'cancelled' => '已停止',
    _ => '尚未开始',
  };
}

Color _statusColor(BuildContext context, String status) {
  final scheme = Theme.of(context).colorScheme;
  return switch (status) {
    'running' || 'stopping' => Colors.orange,
    'awaitingDecision' => Colors.blue,
    'disconnected' || 'failed' => scheme.error,
    'success' => Colors.green,
    _ => scheme.primary,
  };
}

class _RunStatusStrip extends StatelessWidget {
  const _RunStatusStrip({required this.task});

  final Task? task;

  @override
  Widget build(BuildContext context) {
    final status = task?.status ?? 'idle';
    final color = _statusColor(context, status);
    final runId = task?.sessionId ?? task?.taskId;
    final progress = ((task?.progress ?? 0) / 100).clamp(0.0, 1.0).toDouble();
    return Container(
      key: const Key('agentRunStatus'),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                key: const Key('agentRunStatusChip'),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  _statusLabel(status),
                  style: TextStyle(color: color, fontWeight: FontWeight.w600),
                ),
              ),
              const SizedBox(width: 8),
              const Text('阶段', style: TextStyle(fontSize: 12)),
              const SizedBox(width: 4),
              Expanded(
                child: Text(
                  task?.stage ?? '等待任务',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: 8),
              Text('${task?.progress ?? 0}%'),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              const Text('运行 ID', style: TextStyle(fontSize: 12)),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  runId ?? '尚未分配',
                  key: const Key('agentRunId'),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          LinearProgressIndicator(value: progress),
        ],
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
    // The server sends the failure reason in the error payload. Show it in the
    // overview so a failed run is diagnosable without reading the raw event log.
    final rawFailure = status == 'failed' ? task?.errorJson['error'] : null;
    final failure = rawFailure is String && rawFailure.trim().isNotEmpty
        ? rawFailure.trim()
        : null;
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
                Flexible(
                  child: Align(
                    alignment: Alignment.centerRight,
                    child: Chip(
                      label: Text(
                        status,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      side: BorderSide.none,
                      backgroundColor: statusColor.withValues(alpha: 0.16),
                      labelStyle: TextStyle(color: statusColor),
                    ),
                  ),
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
            if (failure != null) ...[
              const SizedBox(height: 18),
              Text('失败原因', style: Theme.of(context).textTheme.bodySmall),
              const SizedBox(height: 6),
              ModelServiceHint(error: failure),
            ],
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

class _EventsCard extends StatefulWidget {
  const _EventsCard({required this.events, required this.task});

  final List<SseEvent> events;
  final Task? task;

  @override
  State<_EventsCard> createState() => _EventsCardState();
}

class _EventsCardState extends State<_EventsCard> {
  final _scrollController = ScrollController();

  @override
  void didUpdateWidget(covariant _EventsCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.events.length != oldWidget.events.length) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!_scrollController.hasClients) return;
        _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
      });
    }
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final active =
        widget.task != null &&
        const {
          'running',
          'awaitingDecision',
          'stopping',
          'disconnected',
        }.contains(widget.task!.status);
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(
                  '实时输出',
                  key: const Key('agentOutputStream'),
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const Spacer(),
                Text(
                  '${widget.events.length} 条',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
            const SizedBox(height: 12),
            Expanded(
              child: widget.events.isEmpty
                  ? Center(
                      child: Text(
                        active ? '已提交，等待服务端流式输出…' : '尚未开始运行',
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                    )
                  : ListView.separated(
                      controller: _scrollController,
                      itemCount: widget.events.length,
                      separatorBuilder: (_, __) => const Divider(height: 16),
                      itemBuilder: (context, index) {
                        final event = widget.events[index];
                        return SelectableText(
                          _eventLabel(event),
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
