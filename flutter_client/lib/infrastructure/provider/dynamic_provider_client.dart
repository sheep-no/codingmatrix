// ignore_for_file: curly_braces_in_flow_control_structures
import '../auth/authenticated_client.dart';

class DynamicProvider {
  const DynamicProvider({
    required this.id,
    required this.name,
    required this.baseUrl,
    required this.protocol,
    required this.enabled,
    required this.models,
    this.syncError = '',
  });
  final String id, name, baseUrl, protocol, syncError;
  final bool enabled;
  final List<String> models;
  factory DynamicProvider.fromJson(Map<String, dynamic> j) => DynamicProvider(
    id: '${j['id']}',
    name: '${j['name']}',
    baseUrl: '${j['base_url']}',
    protocol: '${j['protocol']}',
    enabled: j['enabled'] == true,
    models: [for (final x in (j['models'] as List? ?? const [])) '$x'],
    syncError: '${j['sync_error'] ?? ''}',
  );
}

class DynamicProviderClient {
  DynamicProviderClient(this.api);
  final AuthenticatedClient api;
  Future<List<DynamicProvider>> list() async => [
    for (final x in (await api.requestJson('/api/v1/providers') as List))
      DynamicProvider.fromJson(Map<String, dynamic>.from(x)),
  ];
  Future<void> add({
    required String name,
    required String baseUrl,
    required String protocol,
    required String apiKey,
  }) async => api.requestJson(
    '/api/v1/providers',
    method: 'POST',
    body: {
      'name': name,
      'base_url': baseUrl,
      'protocol': protocol,
      'api_key': apiKey,
    },
  );
  Future<void> toggle(String id) async =>
      api.requestJson('/api/v1/providers/$id/toggle', method: 'PUT');
  Future<void> sync(String id) async =>
      api.requestJson('/api/v1/providers/$id/sync?force=true', method: 'POST');
  Future<void> test(String id) async {
    final result =
        await api.requestJson('/api/v1/providers/$id/test', method: 'POST')
            as Map;
    if (result['success'] != true)
      throw StateError('${result['message'] ?? '连接测试失败'}');
  }

  Future<void> delete(String id) async =>
      api.requestJson('/api/v1/providers/$id', method: 'DELETE');
}
