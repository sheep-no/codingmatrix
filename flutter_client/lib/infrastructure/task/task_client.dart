import '../auth/authenticated_client.dart';

class TaskClient {
  TaskClient(this.api);
  final AuthenticatedClient api;
  Future<List<Map<String, dynamic>>> list() async {
    final data = Map<String, dynamic>.from(
      await api.requestJson('/api/v1/tasks?page=1&page_size=50') as Map,
    );
    return [
      for (final item in (data['tasks'] as List? ?? const []))
        Map<String, dynamic>.from(item),
    ];
  }

  Future<void> cancel(String id) async => api.requestJson(
    '/api/v1/tasks/${Uri.encodeComponent(id)}',
    method: 'DELETE',
  );
  Future<void> retry(String id) async => api.requestJson(
    '/api/v1/tasks/${Uri.encodeComponent(id)}/retry',
    method: 'POST',
  );

  Future<List<Map<String, dynamic>>> events(String id) async {
    final value = Map<String, dynamic>.from(
      await api.requestJson('/api/v1/tasks/${Uri.encodeComponent(id)}/events')
          as Map,
    );
    return [
      for (final item in (value['events'] as List? ?? const []))
        Map<String, dynamic>.from(item),
    ];
  }
}
