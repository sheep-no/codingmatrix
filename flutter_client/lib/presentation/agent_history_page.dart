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
