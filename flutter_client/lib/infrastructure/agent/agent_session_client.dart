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
}
