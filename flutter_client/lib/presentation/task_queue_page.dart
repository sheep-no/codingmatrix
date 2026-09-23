// ignore_for_file: curly_braces_in_flow_control_structures
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/auth_controller.dart';
import '../infrastructure/task/task_client.dart';
import 'account_overlays.dart';
import 'shell_scaffold.dart';

class TaskQueuePage extends ConsumerStatefulWidget {
  const TaskQueuePage({super.key});
  @override
  ConsumerState<TaskQueuePage> createState() => _TaskQueuePageState();
}

class _TaskQueuePageState extends ConsumerState<TaskQueuePage> {
  List<Map<String, dynamic>> items = const [];
  bool loading = true;
  bool busy = false;
  String? error;
  // Bumped whenever the account context changes so a response that arrives
  // after the switch cannot write into the new account's page state.
  int _epoch = 0;
  TaskClient get client => TaskClient(ref.read(authenticatedClientProvider));
  @override
  void initState() {
    super.initState();
    Future.microtask(load);
  }

  Future<void> load() async {
    if (!mounted) return;
    final epoch = _epoch;
    setState(() => loading = true);
    try {
      final result = await client.list();
      if (!mounted || epoch != _epoch) return;
      setState(() {
        items = result;
        error = null;
        loading = false;
      });
    } catch (e) {
      if (!mounted || epoch != _epoch) return;
      setState(() {
        error = '$e';
        loading = false;
      });
    }
  }

  void _resetAccount() {
    _epoch++;
    closeAccountOverlays(context);
    setState(() {
      items = const [];
      error = null;
      busy = false;
    });
    load();
  }

  Future<void> action(Future<void> Function() call) async {
    if (busy || loading || !mounted) return;
    final epoch = _epoch;
    setState(() => busy = true);
    try {
      await call();
      if (epoch != _epoch) return;
      await load();
    } catch (e) {
      if (mounted && epoch == _epoch)
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('$e')));
    } finally {
      if (mounted && epoch == _epoch) setState(() => busy = false);
    }
  }

  Future<void> showEvents(String id) async {
    if (busy || loading || !mounted) return;
    final epoch = _epoch;
    setState(() => busy = true);
    try {
      final events = await client.events(id);
      if (!mounted || epoch != _epoch) return;
      showModalBottomSheet<void>(
        context: context,
        builder: (_) => ListView(
          children: [
            if (events.isEmpty)
              const ListTile(dense: true, title: Text('暂无事件')),
            for (final event in events)
              ListTile(
                title: Text(
                  '${event['event_type'] ?? event['status'] ?? '事件'}',
                ),
                subtitle: Text(
                  '${event['created_at'] ?? ''}\n${event['payload'] ?? ''}',
                ),
                isThreeLine: true,
              ),
          ],
        ),
      );
    } catch (e) {
      if (mounted && epoch == _epoch)
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('事件读取失败：$e')));
    } finally {
      if (mounted && epoch == _epoch) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(
      authControllerProvider.select((s) => s.session?.accessTokenRef),
      (_, __) => _resetAccount(),
    );
    ref.listen(apiBaseUrlProvider, (_, __) => _resetAccount());
    return ShellScaffold(
      title: '任务队列',
      actions: [
        IconButton(
          onPressed: (busy || loading) ? null : load,
          icon: const Icon(Icons.refresh),
        ),
      ],
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : error != null
          ? Center(child: Text(error!))
          : items.isEmpty
          ? const Center(child: Text('暂无任务'))
          : ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: items.length,
              itemBuilder: (_, i) {
                final task = items[i];
                final status = '${task['status'] ?? 'unknown'}';
                final id = '${task['task_id']}';
                final canCancel = [
                  'pending',
                  'running',
                  'retrying',
                ].contains(status);
                final canRetry = ['failed', 'error'].contains(status);
                return Card(
                  child: ListTile(
                    title: Text('${task['task_type'] ?? '任务'} · $status'),
                    subtitle: Text(
                      '$id\n${task['progress_message'] ?? ''} ${task['progress'] ?? 0}%',
                    ),
                    isThreeLine: true,
                    trailing: Wrap(
                      children: [
                        IconButton(
                          tooltip: '查看事件',
                          onPressed: busy ? null : () => showEvents(id),
                          icon: const Icon(Icons.list_alt),
                        ),
                        if (canCancel)
                          IconButton(
                            tooltip: '取消',
                            onPressed: busy
                                ? null
                                : () => action(() => client.cancel(id)),
                            icon: const Icon(Icons.stop),
                          ),
                        if (canRetry)
                          IconButton(
                            tooltip: '重试',
                            onPressed: busy
                                ? null
                                : () => action(() => client.retry(id)),
                            icon: const Icon(Icons.refresh),
                          ),
                      ],
                    ),
                  ),
                );
              },
            ),
    );
  }
}
