// ignore_for_file: curly_braces_in_flow_control_structures
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/agent_session_providers.dart';
import '../application/auth_controller.dart';
import '../application/workbench_controller.dart';
import '../infrastructure/agent/agent_session_client.dart';
import 'account_overlays.dart';
import 'agent_stats_dialog.dart';
import 'dialog_controllers.dart';
import 'project_files_page.dart';
import 'shell_scaffold.dart';

class AgentHistoryPage extends ConsumerStatefulWidget {
  const AgentHistoryPage({super.key});
  @override
  ConsumerState<AgentHistoryPage> createState() => _AgentHistoryPageState();
}

class _AgentHistoryPageState extends ConsumerState<AgentHistoryPage> {
  bool busy = false;
  // Bumped on account change so a late stats/mutation result cannot open a
  // dialog or message belonging to the previous account.
  int _epoch = 0;

  void _resetAccount() {
    _epoch++;
    closeAccountOverlays(context);
    setState(() => busy = false);
  }

  Future<void> run(String failure, Future<void> Function() action) async {
    if (busy || !mounted) return;
    final epoch = _epoch;
    setState(() => busy = true);
    try {
      await action();
    } catch (e) {
      if (mounted && epoch == _epoch)
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('$failure：$e')));
    } finally {
      if (mounted && epoch == _epoch) setState(() => busy = false);
    }
  }

  Future<void> showStats() {
    final epoch = _epoch;
    return run('统计读取失败', () async {
      final api = ref.read(authenticatedClientProvider);
      final results = await Future.wait([
        api.requestJson('/api/v1/agent/token-usage'),
        api.requestJson('/api/v1/agent/cache/stats'),
        api.requestJson('/api/v1/agent/learning/stats'),
        api.requestJson('/api/v1/agent/concurrent-limits/recommended'),
      ]);
      if (!mounted || epoch != _epoch) return;
      showDialog<void>(
        context: context,
        builder: (_) => AgentStatsDialog(
          usage: results[0],
          cache: results[1],
          learning: results[2],
          limits: results[3],
        ),
      );
    });
  }

  Future<void> clearCache() => run('缓存清理失败', () async {
    final epoch = _epoch;
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
    if (confirmed != true || !mounted) return;
    await ref
        .read(authenticatedClientProvider)
        .requestJson('/api/v1/agent/cache/clear', method: 'POST');
    if (mounted && epoch == _epoch)
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('缓存清理请求已提交')));
  });

  Future<void> updateLimit() => run('更新失败', () async {
    final epoch = _epoch;
    final api = ref.read(authenticatedClientProvider);
    final updated = await showDialog<bool>(
      context: context,
      builder: (_) => _ConcurrentLimitDialog(
        onSave: (role, limit) => api.requestJson(
          '/api/v1/agent/concurrent-limits'
          '?role=${Uri.encodeQueryComponent(role)}&new_limit=$limit',
          method: 'PUT',
        ),
      ),
    );
    if (updated != true || !mounted || epoch != _epoch) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('并发限制已更新')));
  });

  @override
  Widget build(BuildContext context) {
    ref.listen(
      authControllerProvider.select((s) => s.session?.accessTokenRef),
      (_, __) => _resetAccount(),
    );
    ref.listen(apiBaseUrlProvider, (_, __) => _resetAccount());
    return ShellScaffold(
      title: '会话历史',
      actions: [
        IconButton(
          tooltip: 'Agent 统计',
          icon: const Icon(Icons.analytics_outlined),
          onPressed: busy ? null : showStats,
        ),
        IconButton(
          tooltip: '清理缓存',
          icon: const Icon(Icons.cleaning_services_outlined),
          onPressed: busy ? null : clearCache,
        ),
        IconButton(
          tooltip: '并发限制',
          icon: const Icon(Icons.tune),
          onPressed: busy ? null : updateLimit,
        ),
        IconButton(
          tooltip: '刷新',
          icon: const Icon(Icons.refresh),
          onPressed: busy ? null : () => ref.invalidate(agentSessionsProvider),
        ),
      ],
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
}

class AgentSessionDetailPage extends ConsumerStatefulWidget {
  const AgentSessionDetailPage({super.key, required this.id});
  final String id;
  @override
  ConsumerState<AgentSessionDetailPage> createState() => _DetailState();
}

class _DetailState extends ConsumerState<AgentSessionDetailPage> {
  bool busy = false;
  bool snapshotsBusy = false;
  String? error;
  // Bumped on account change so an in-flight snapshot/diff/rollback result
  // cannot open an overlay or write state for the previous account.
  int _epoch = 0;

  void _resetAccount() {
    _epoch++;
    closeAccountOverlays(context);
    setState(() {
      busy = false;
      snapshotsBusy = false;
    });
  }

  Future<void> showSnapshots(String id) async {
    if (snapshotsBusy || !mounted) return;
    final epoch = _epoch;
    setState(() {
      snapshotsBusy = true;
      error = null;
    });
    try {
      final items = await ref.read(agentSessionClientProvider).snapshots(id);
      if (!mounted || epoch != _epoch) return;
      showModalBottomSheet<void>(
        context: context,
        builder: (sheetContext) => ListView(
          children: [
            if (items.isEmpty) const ListTile(dense: true, title: Text('暂无快照')),
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
                    final rollbackEpoch = _epoch;
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
                      if (mounted && rollbackEpoch == _epoch)
                        setState(() => error = null);
                      try {
                        await ref
                            .read(agentSessionClientProvider)
                            .rollback(id, tag);
                        if (mounted && rollbackEpoch == _epoch)
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('回滚请求已提交')),
                          );
                      } catch (e) {
                        if (mounted && rollbackEpoch == _epoch)
                          setState(() => error = '回滚失败：$e');
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
                  final diffEpoch = _epoch;
                  final from =
                      '${items[items.length - 2]['tag'] ?? items[items.length - 2]['id'] ?? ''}';
                  final to = '${items.last['tag'] ?? items.last['id'] ?? ''}';
                  Navigator.pop(sheetContext);
                  if (mounted && diffEpoch == _epoch)
                    setState(() => error = null);
                  try {
                    final diff = await ref
                        .read(agentSessionClientProvider)
                        .diff(id, from, to);
                    if (!mounted || diffEpoch != _epoch) return;
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
                    if (mounted && diffEpoch == _epoch)
                      setState(() => error = '差异读取失败：$e');
                  }
                },
              ),
          ],
        ),
      );
    } catch (e) {
      if (mounted && epoch == _epoch) setState(() => error = '快照读取失败：$e');
    } finally {
      if (mounted && epoch == _epoch) setState(() => snapshotsBusy = false);
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
  Widget build(BuildContext context) {
    ref.listen(
      authControllerProvider.select((s) => s.session?.accessTokenRef),
      (_, __) => _resetAccount(),
    );
    ref.listen(apiBaseUrlProvider, (_, __) => _resetAccount());
    return Scaffold(
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
                  onPressed: snapshotsBusy
                      ? null
                      : () => showSnapshots(session.id),
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
}

/// 并发限制弹窗：本地校验正整数，失败时保留弹窗和输入。
class _ConcurrentLimitDialog extends StatefulWidget {
  const _ConcurrentLimitDialog({required this.onSave});

  final Future<Object?> Function(String role, int limit) onSave;

  @override
  State<_ConcurrentLimitDialog> createState() => _ConcurrentLimitDialogState();
}

class _ConcurrentLimitDialogState extends State<_ConcurrentLimitDialog> {
  final role = TextEditingController(text: 'default');
  final limit = TextEditingController(text: '1');
  String? roleError;
  String? limitError;
  String? error;
  String? hint;
  bool busy = false;

  @override
  void dispose() {
    role.dispose();
    limit.dispose();
    super.dispose();
  }

  Future<void> save() async {
    if (busy) return;
    final roleValue = role.text.trim();
    final limitValue = int.tryParse(limit.text.trim());
    setState(() {
      roleError = roleValue.isEmpty ? '请输入角色' : null;
      limitError = limitValue == null || limitValue < 1 ? '限制值必须为正整数' : null;
      error = null;
      hint = null;
    });
    if (roleError != null || limitError != null) return;

    setState(() => busy = true);
    try {
      await widget.onSave(roleValue, limitValue!);
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        busy = false;
        error = '更新失败';
        hint = '$e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('调整并发限制'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: role,
              enabled: !busy,
              decoration: InputDecoration(
                labelText: '角色',
                errorText: roleError,
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: limit,
              enabled: !busy,
              keyboardType: TextInputType.number,
              decoration: InputDecoration(
                labelText: '限制值',
                errorText: limitError,
              ),
            ),
            if (error != null) DialogErrorNotice(message: error!, detail: hint),
            if (busy)
              const Padding(
                padding: EdgeInsets.only(top: 12),
                child: LinearProgressIndicator(),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: busy ? null : () => Navigator.pop(context),
          child: const Text('取消'),
        ),
        FilledButton(
          onPressed: busy ? null : save,
          child: Text(busy ? '保存中…' : '保存'),
        ),
      ],
    );
  }
}
