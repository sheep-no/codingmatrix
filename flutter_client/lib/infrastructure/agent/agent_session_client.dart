import '../auth/authenticated_client.dart';

class AgentSession {
  AgentSession.fromJson(Map<String, dynamic> json)
    : id = json['session_id'] as String,
      requirement = json['requirement'] as String? ?? '',
      status = json['status'] as String? ?? 'unknown',
      projectPath = json['output_dir'] as String?,
      error = json['error_message'] as String?,
      updatedAt = json['updated_at'] as String?,
      generated = (json['files_generated'] as num?)?.toInt() ?? 0,
      total = (json['files_total'] as num?)?.toInt() ?? 0,
      reconnectable = json['reconnectable'] == true;
  final String id, requirement, status;
  final String? projectPath, error, updatedAt;
  final int generated, total;
  final bool reconnectable;
}

class AgentSessionClient {
  AgentSessionClient(this.api);
  final AuthenticatedClient api;

  Future<List<AgentSession>> list() async {
    final json = await api.requestJson('/api/v1/agent/sessions') as Map;
    return (json['sessions'] as List)
        .map(
          (item) =>
              AgentSession.fromJson(Map<String, dynamic>.from(item as Map)),
        )
        .toList();
  }

  Future<AgentSession> detail(String id) async => AgentSession.fromJson(
    Map<String, dynamic>.from(
      await api.requestJson('/api/v1/agent/sessions/${Uri.encodeComponent(id)}')
          as Map,
    ),
  );

  Future<List<Map<String, dynamic>>> snapshots(String id) async {
    final value =
        await api.requestJson(
              '/api/v1/agent/snapshots/${Uri.encodeComponent(id)}',
            )
            as Map;
    return [
      for (final item in (value['snapshots'] as List? ?? const []))
        Map<String, dynamic>.from(item),
    ];
  }

  Future<void> rollback(String id, String tag) async => api.requestJson(
    '/api/v1/agent/rollback/${Uri.encodeComponent(id)}?target_tag=${Uri.encodeQueryComponent(tag)}',
    method: 'POST',
  );

  Future<String> diff(String id, String fromTag, String toTag) async {
    final value =
        await api.requestJson(
              '/api/v1/agent/snapshot/diff?session_id=${Uri.encodeQueryComponent(id)}&from_tag=${Uri.encodeQueryComponent(fromTag)}&to_tag=${Uri.encodeQueryComponent(toTag)}',
            )
            as Map;
    return '${value['diff'] ?? ''}';
  }
}
