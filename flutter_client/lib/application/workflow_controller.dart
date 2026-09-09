import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../domain/models/workflow_models.dart';
import '../infrastructure/workflow/workflow_client.dart';
import 'auth_controller.dart';

class WorkflowState {
  const WorkflowState({
    this.snapshot = const WorkflowSnapshot(),
    this.active = false,
    this.refreshing = false,
    this.error,
    this.events = const [],
  });
  final WorkflowSnapshot snapshot;
  final bool active, refreshing;
  final String? error;
  final List<String> events;
}

class WorkflowController extends StateNotifier<WorkflowState> {
  WorkflowController(this.client) : super(const WorkflowState());
  final WorkflowClient client;
  StreamSubscription<Map<String, dynamic>>? _subscription;
  int _operation = 0;
  bool _current(int op) => mounted && op == _operation;
  Future<void> execute(String input, {int timeout = 1800}) async {
    if (!mounted || state.active || state.refreshing) return;
    if (input.trim().isEmpty || timeout < 60 || timeout > 3600) {
      state = const WorkflowState(error: '请输入任务描述，超时范围为 60 至 3600 秒');
      return;
    }
    final op = ++_operation;
    state = const WorkflowState(
      active: true,
      snapshot: WorkflowSnapshot(status: 'connecting'),
    );
    try {
      final stream = await client.execute(input, timeout);
      if (!_current(op)) {
        await stream.take(0).drain<void>();
        return;
      }
      _subscription = stream.listen(
        (event) {
          if (!_current(op) || !state.active) return;
          try {
            _ingest(event);
          } catch (_) {
            _failed(op, '工作流事件格式异常，执行结果未知');
          }
        },
        onError: (Object _) => _failed(op, '工作流连接中断，执行结果未知，可查询状态'),
        onDone: () {
          if (_current(op) && state.active) _failed(op, '响应提前结束，执行结果未知，可查询状态');
        },
      );
    } catch (_) {
      _failed(op, '执行请求失败或结果未知，请先核对任务状态');
    }
  }

  void _ingest(Map<String, dynamic> event) {
    final old = state.snapshot;
    final type = event['event'] as String;
    final id = event['workflow_id'];
    var nodes = old.nodes;
    var status = old.status;
    Object? summary = old.summary;
    String? error;
    var active = true;
    switch (type) {
      case 'workflow_started':
        status = 'running';
      case 'task_graph_generated':
        nodes = (event['nodes'] as List)
            .map(
              (n) => WorkflowNode.fromJson(Map<String, dynamic>.from(n as Map)),
            )
            .toList();
        status = 'running';
      case 'node_started':
      case 'node_completed':
        nodes = nodes
            .map((n) => n.id == event['node_id'] ? n.update(event) : n)
            .toList();
      case 'workflow_completed':
        status = event['status'] as String? ?? 'unknown';
        summary = event['summary'];
        active = false;
      case 'workflow_error':
        status = 'failed';
        error = '工作流执行失败，请检查输入或服务配置';
        active = false;
    }
    state = WorkflowState(
      active: active,
      error: error,
      snapshot: WorkflowSnapshot(
        id: id is String && id != 'pending' ? id : old.id,
        status: status,
        nodes: nodes,
        summary: summary,
      ),
      events: [
        ...state.events,
        type,
      ].reversed.take(100).toList().reversed.toList(),
    );
    if (!active) {
      unawaited(_subscription?.cancel());
      _subscription = null;
    }
  }

  void _failed(int op, String message) {
    if (!_current(op) || !state.active) return;
    final old = state.snapshot;
    state = WorkflowState(
      snapshot: WorkflowSnapshot(
        id: old.id,
        status: 'disconnected',
        nodes: old.nodes,
        summary: old.summary,
      ),
      events: state.events,
      error: message,
    );
    unawaited(_subscription?.cancel());
    _subscription = null;
  }

  Future<void> disconnect() async {
    if (!mounted) return;
    ++_operation;
    final old = state.snapshot;
    state = WorkflowState(
      snapshot: WorkflowSnapshot(
        id: old.id,
        status: old.terminal ? old.status : 'disconnected',
        nodes: old.nodes,
        summary: old.summary,
      ),
      events: state.events,
      error: '本地连接已断开，服务端可能继续执行；可查询状态',
    );
    final subscription = _subscription;
    _subscription = null;
    await subscription?.cancel();
  }

  Future<void> refresh() async {
    if (!mounted ||
        state.active ||
        state.refreshing ||
        state.snapshot.id == null) {
      return;
    }
    final op = ++_operation;
    final previous = state;
    state = WorkflowState(
      snapshot: previous.snapshot,
      refreshing: true,
      events: previous.events,
    );
    try {
      final snapshot = await client.status(previous.snapshot.id!);
      if (_current(op)) {
        state = WorkflowState(snapshot: snapshot, events: previous.events);
      }
    } catch (_) {
      if (_current(op)) {
        state = WorkflowState(
          snapshot: previous.snapshot,
          events: previous.events,
          error: '状态查询失败；任务可能已过期或当前服务进程没有记录',
        );
      }
    }
  }

  @override
  void dispose() {
    ++_operation;
    unawaited(_subscription?.cancel());
    super.dispose();
  }
}

final workflowControllerProvider =
    StateNotifierProvider.autoDispose<WorkflowController, WorkflowState>((ref) {
      ref.watch(
        authControllerProvider.select((s) => s.session?.accessTokenRef),
      );
      ref.watch(apiBaseUrlProvider);
      return WorkflowController(
        WorkflowClient(ref.watch(authenticatedClientProvider)),
      );
    });
