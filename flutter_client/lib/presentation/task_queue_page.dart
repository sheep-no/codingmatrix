// ignore_for_file: curly_braces_in_flow_control_structures
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/auth_controller.dart';
import '../infrastructure/task/task_client.dart';

class TaskQueuePage extends ConsumerStatefulWidget {
  const TaskQueuePage({super.key});
  @override
  ConsumerState<TaskQueuePage> createState() => _TaskQueuePageState();
}

class _TaskQueuePageState extends ConsumerState<TaskQueuePage> {
  List<Map<String, dynamic>> items = const [];
  bool loading = true;
  String? error;
  TaskClient get client => TaskClient(ref.read(authenticatedClientProvider));
  @override
  void initState() {
    super.initState();
    Future.microtask(load);
  }

  Future<void> load() async {
    setState(() => loading = true);
    try {
      final result = await client.list();
      if (mounted)
        setState(() {
          items = result;
          error = null;
          loading = false;
        });
    } catch (e) {
      if (mounted)
        setState(() {
          error = '$e';
          loading = false;
        });
    }
  }

  Future<void> action(Future<void> Function() call) async {
    try {
      await call();
      await load();
    } catch (e) {
      if (mounted)
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  Future<void> showEvents(String id) async {
    try {
      final events = await client.events(id);
      if (!mounted) return;
      showModalBottomSheet<void>(
        context: context,
        builder: (_) => ListView(
          children: [
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
      if (mounted)
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('事件读取失败：$e')));
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('任务队列'),
      actions: [
        IconButton(
          onPressed: loading ? null : load,
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: loading
        ? const Center(child: CircularProgressIndicator())
        : error != null
        ? Center(child: Text(error!))
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
                        onPressed: () => showEvents(id),
                        icon: const Icon(Icons.list_alt),
                      ),
                      if (canCancel)
                        IconButton(
                          tooltip: '取消',
                          onPressed: () => action(() => client.cancel(id)),
                          icon: const Icon(Icons.stop),
                        ),
                      if (canRetry)
                        IconButton(
                          tooltip: '重试',
                          onPressed: () => action(() => client.retry(id)),
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
