class WorkflowNode {
  const WorkflowNode({
    required this.id,
    required this.type,
    this.dependencies = const [],
    this.params = const {},
    this.status = 'pending',
    this.result,
    this.error,
  });
  factory WorkflowNode.fromJson(Map<String, dynamic> json) => WorkflowNode(
    id: json['id'] as String,
    type: json['type'] as String,
    dependencies: List<String>.from(json['depends_on'] as List? ?? []),
    params: Map<String, dynamic>.from(json['params'] as Map? ?? {}),
    status: json['status'] as String? ?? 'pending',
    result: json['result'],
    error: json['error'] as String?,
  );
  final String id, type, status;
  final List<String> dependencies;
  final Map<String, dynamic> params;
  final Object? result;
  final String? error;
  WorkflowNode update(Map<String, dynamic> event) => WorkflowNode(
    id: id,
    type: type,
    dependencies: dependencies,
    params: params,
    status: event['event'] == 'node_started'
        ? 'running'
        : event['success'] == true
        ? 'completed'
        : 'failed',
    result: event['data'],
    error: event['error'] as String?,
  );
}

class WorkflowSnapshot {
  const WorkflowSnapshot({
    this.id,
    this.status = 'idle',
    this.nodes = const [],
    this.summary,
  });
  factory WorkflowSnapshot.fromJson(Map<String, dynamic> json) =>
      WorkflowSnapshot(
        id: json['workflow_id'] as String,
        status: json['status'] as String,
        nodes: ((json['task_graph'] as Map?)?['nodes'] as List? ?? [])
            .map(
              (e) => WorkflowNode.fromJson(Map<String, dynamic>.from(e as Map)),
            )
            .toList(),
        summary: json['summary'],
      );
  final String? id;
  final String status;
  final List<WorkflowNode> nodes;
  final Object? summary;
  bool get terminal => [
    'completed',
    'failed',
    'cancelled',
    'partial_success',
    'timeout',
  ].contains(status);
}
