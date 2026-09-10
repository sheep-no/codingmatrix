// ignore_for_file: curly_braces_in_flow_control_structures
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/agent_session_providers.dart';
import '../application/auth_controller.dart';
import '../application/workbench_controller.dart';
import '../infrastructure/agent/agent_session_client.dart';
import 'project_files_page.dart';

class AgentHistoryPage extends ConsumerWidget {
  const AgentHistoryPage({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(
      title: const Text('会话历史'),
      actions: [
        IconButton(
          tooltip: 'Agent 统计',
          icon: const Icon(Icons.analytics_outlined),
          onPressed: () async {
            try {
              final api = ref.read(authenticatedClientProvider);
              final results = await Future.wait([
                api.requestJson('/api/v1/agent/token-usage'),
                api.requestJson('/api/v1/agent/cache/stats'),
                api.requestJson('/api/v1/agent/learning/stats'),
                api.requestJson('/api/v1/agent/concurrent-limits/recommended'),
              ]);
              if (!context.mounted) return;
              showDialog<void>(
                context: context,
                builder: (_) => AlertDialog(
                  title: const Text('Agent 统计'),
                  content: SingleChildScrollView(
                    child: Text(results.map((item) => '$item').join('\n\n')),
                  ),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(context),
                      child: const Text('关闭'),
                    ),
                  ],
                ),
              );
            } catch (e) {
              if (context.mounted)
                ScaffoldMessenger.of(
                  context,
                ).showSnackBar(SnackBar(content: Text('统计读取失败：$e')));
            }
          },
        ),
        IconButton(
          tooltip: '清理缓存',
          icon: const Icon(Icons.cleaning_services_outlined),
          onPressed: () async {
            final confirmed = await showDialog<bool>(
              context: context,
              builder: (dialogContext) => AlertDialog(
                title: const Text('清理 Agent 缓存'),
                content: const Text('确认清理当前 Agent 缓存吗？'),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(dialogContext, false),
                    child: const Text('取消'),
                  ),
                  FilledButton(
                    onPressed: () => Navigator.pop(dialogContext, true),
                    child: const Text('清理'),
                  ),
                ],
              ),
            );
            if (confirmed != true || !context.mounted) return;
            try {
              await ref
                  .read(authenticatedClientProvider)
                  .requestJson('/api/v1/agent/cache/clear', method: 'POST');
              if (context.mounted)
                ScaffoldMessenger.of(
                  context,
                ).showSnackBar(const SnackBar(content: Text('缓存清理请求已提交')));
            } catch (e) {
              if (context.mounted)
                ScaffoldMessenger.of(
                  context,
                ).showSnackBar(SnackBar(content: Text('缓存清理失败：$e')));
            }
          },
        ),
        IconButton(
          tooltip: '并发限制',
          icon: const Icon(Icons.tune),
          onPressed: () async {
            final roleController = TextEditingController(text: 'default');
            final limitController = TextEditingController(text: '1');
            final accepted = await showDialog<bool>(
              context: context,
              builder: (dialogContext) => AlertDialog(
                title: const Text('调整并发限制'),
                content: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    TextField(
                      controller: roleController,
                      decoration: const InputDecoration(labelText: '角色'),
                    ),
                    TextField(
                      controller: limitController,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(labelText: '限制值'),
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
            );
            final role = roleController.text.trim();
            final limit = int.tryParse(limitController.text.trim());
            roleController.dispose();
            limitController.dispose();
            if (accepted != true ||
                role.isEmpty ||
                limit == null ||
                !context.mounted)
              return;
            try {
              await ref
                  .read(authenticatedClientProvider)
                  .requestJson(
                    '/api/v1/agent/concurrent-limits?role=${Uri.encodeQueryComponent(role)}&new_limit=$limit',
                    method: 'PUT',
                  );
              if (context.mounted)
                ScaffoldMessenger.of(
                  context,
                ).showSnackBar(const SnackBar(content: Text('并发限制已更新')));
            } catch (e) {
              if (context.mounted)
                ScaffoldMessenger.of(
                  context,
                ).showSnackBar(SnackBar(content: Text('更新失败：$e')));
            }
          },
        ),
        IconButton(
          tooltip: '刷新',
          icon: const Icon(Icons.refresh),
          onPressed: () => ref.invalidate(agentSessionsProvider),
        ),
      ],
    ),
    body: ref
        .watch(agentSessionsProvider)
        .when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (_, _) => Center(
            child: TextButton(
              onPressed: () => ref.invalidate(agentSessionsProvider),
              child: const Text('加载失败，点击重试'),
            ),
          ),
          data: (sessions) => sessions.isEmpty
              ? const Center(child: Text('暂无会话'))
              : ListView.builder(
                  itemCount: sessions.length,
                  itemBuilder: (context, index) {
                    final session = sessions[index];
                    return ListTile(
                      title: Text(
                        session.requirement,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      subtitle: Text(
                        '${session.status} · ${session.generated}/${session.total}\n${session.updatedAt ?? session.id}',
                      ),
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) =>
                              AgentSessionDetailPage(id: session.id),
                        ),
                      ),
                    );
                  },
                ),
        ),
  );
}

class AgentSessionDetailPage extends ConsumerStatefulWidget {
  const AgentSessionDetailPage({super.key, required this.id});
  final String id;
  @override
  ConsumerState<AgentSessionDetailPage> createState() => _DetailState();
}

class _DetailState extends ConsumerState<AgentSessionDetailPage> {
  bool busy = false;
  String? error;
  Future<void> showSnapshots(String id) async {
    try {
      final items = await ref.read(agentSessionClientProvider).snapshots(id);
      if (!mounted) return;
      showModalBottomSheet<void>(
        context: context,
        builder: (sheetContext) => ListView(
          children: [
            for (final item in items)
              ListTile(
                title: Text('${item['tag'] ?? item['id'] ?? '快照'}'),
                subtitle: Text(
                  '${item['message'] ?? item['created_at'] ?? ''}',
                ),
                trailing: IconButton(
                  tooltip: '回滚',
                  icon: const Icon(Icons.restore),
                  onPressed: () async {
                    final tag = '${item['tag'] ?? item['id'] ?? ''}';
                    if (tag.isEmpty) return;
                    Navigator.pop(sheetContext);
                    final confirmed = await showDialog<bool>(
                      context: context,
                      builder: (dialogContext) => AlertDialog(
                        title: const Text('确认回滚'),
                        content: Text('将回滚到快照 $tag，当前未提交修改可能丢失。'),
                        actions: [
                          TextButton(
                            onPressed: () =>
                                Navigator.pop(dialogContext, false),
                            child: const Text('取消'),
                          ),
                          FilledButton(
                            onPressed: () => Navigator.pop(dialogContext, true),
                            child: const Text('确认'),
                          ),
                        ],
                      ),
                    );
                    if (confirmed == true) {
                      try {
                        await ref
                            .read(agentSessionClientProvider)
                            .rollback(id, tag);
                        if (mounted)
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('回滚请求已提交')),
                          );
                      } catch (e) {
                        if (mounted) setState(() => error = '回滚失败：$e');
                      }
                    }
                  },
                ),
              ),
            if (items.length >= 2)
              ListTile(
                leading: const Icon(Icons.compare_arrows),
                title: const Text('比较最新两个快照'),
                onTap: () async {
                  final from =
                      '${items[items.length - 2]['tag'] ?? items[items.length - 2]['id'] ?? ''}';
                  final to = '${items.last['tag'] ?? items.last['id'] ?? ''}';
                  Navigator.pop(sheetContext);
                  try {
                    final diff = await ref
                        .read(agentSessionClientProvider)
                        .diff(id, from, to);
                    if (!mounted) return;
                    showDialog<void>(
                      context: context,
                      builder: (dialogContext) => AlertDialog(
                        title: const Text('快照差异'),
                        content: SizedBox(
                          width: double.maxFinite,
                          child: SingleChildScrollView(
                            child: SelectableText(diff.isEmpty ? '没有差异' : diff),
                          ),
                        ),
                        actions: [
                          TextButton(
                            onPressed: () => Navigator.pop(dialogContext),
                            child: const Text('关闭'),
                          ),
                        ],
                      ),
                    );
                  } catch (e) {
                    if (mounted) setState(() => error = '差异读取失败：$e');
                  }
                },
              ),
          ],
        ),
      );
    } catch (e) {
      if (mounted) setState(() => error = '快照读取失败：$e');
    }
  }

  Future<void> reconnect(AgentSession session) async {
    final account = ref.read(authControllerProvider).session?.accessTokenRef;
    if (account == null || busy) return;
    final controller = ref.read(workbenchControllerProvider.notifier);
    setState(() {
      busy = true;
      error = null;
    });
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('恢复事件连接？'),
        content: const Text(
          '将断开工作台当前本地订阅，服务端任务继续运行。仅接收所选存活任务的后续及未消费事件；已消费事件和决策无法重放。',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('断开并重连'),
          ),
        ],
      ),
    );
    try {
      if (!mounted ||
          confirmed != true ||
          ref.read(authControllerProvider).session?.accessTokenRef != account) {
        return;
      }
      final latest = await ref
          .read(agentSessionClientProvider)
          .detail(session.id);
      if (!mounted ||
          ref.read(authControllerProvider).session?.accessTokenRef != account) {
        return;
      }
      if (!latest.reconnectable) throw StateError('任务已结束或当前进程无可重连任务，请刷新详情');
      await controller.startGeneration(
        accessTokenRef: account,
        requirement: latest.requirement.isEmpty ? '恢复事件连接' : latest.requirement,
        resumeSessionId: latest.id,
      );
      if (mounted) Navigator.of(context).popUntil((route) => route.isFirst);
    } catch (_) {
      if (mounted) setState(() => error = '恢复未成功，请刷新详情后重试');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('会话详情'),
      actions: [
        IconButton(
          tooltip: '刷新状态',
          icon: const Icon(Icons.refresh),
          onPressed: () =>
              ref.invalidate(agentSessionDetailProvider(widget.id)),
        ),
      ],
    ),
    body: ref
        .watch(agentSessionDetailProvider(widget.id))
        .when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (_, _) => Center(
            child: TextButton(
              onPressed: () =>
                  ref.invalidate(agentSessionDetailProvider(widget.id)),
              child: const Text('状态查询失败，点击重试'),
            ),
          ),
          data: (session) => ListView(
            padding: const EdgeInsets.all(16),
            children: [
              SelectableText(session.requirement),
              const SizedBox(height: 16),
              Text(
                '会话：${session.id}\n状态：${session.status}\n文件：${session.generated}/${session.total}',
              ),
              if (session.projectPath?.isNotEmpty == true &&
                  session.status != 'cancelled')
                OutlinedButton(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) =>
                          ProjectFilesPage(project: session.projectPath!),
                    ),
                  ),
                  child: const Text('查看项目文件'),
                ),
              OutlinedButton(
                onPressed: () => showSnapshots(session.id),
                child: const Text('查看快照'),
              ),
              if (session.error != null) Text(session.error!),
              const Text('仅支持当前进程存活任务重连。历史事件、决策重放和进程重启续跑尚无可用契约。'),
              if (error != null) Text(error!),
              FilledButton(
                onPressed: session.reconnectable && !busy
                    ? () => reconnect(session)
                    : null,
                child: Text(busy ? '正在确认' : '恢复 SSE 连接'),
              ),
            ],
          ),
        ),
  );
}
