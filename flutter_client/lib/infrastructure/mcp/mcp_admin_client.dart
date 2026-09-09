import '../auth/authenticated_client.dart';

class McpAdminClient {
  McpAdminClient(this.client);
  final AuthenticatedClient client;

  Future<List<Map<String, dynamic>>> listServers() async {
    final value = await client.requestJson('/api/v2/mcp/servers');
    final data = Map<String, dynamic>.from(value as Map);
    return (data['servers'] as List? ?? const [])
        .map((item) => Map<String, dynamic>.from(item as Map))
        .toList();
  }

  Future<void> addServer({
    required String name,
    required String transport,
    String? command,
    String? url,
  }) async {
    await client.requestJson(
      '/api/v2/mcp/servers',
      method: 'POST',
      body: {
        'name': name,
        'transport': transport,
        'enabled': true,
        if (command != null && command.isNotEmpty) 'command': command,
        if (url != null && url.isNotEmpty) 'url': url,
      },
    );
  }

  Future<Map<String, dynamic>> toggle(String name) async {
    final value = await client.requestJson(
      '/api/v2/mcp/servers/${Uri.encodeComponent(name)}/toggle',
      method: 'POST',
    );
    return Map<String, dynamic>.from(value as Map);
  }

  Future<Map<String, dynamic>> test(String name) async {
    final value = await client.requestJson(
      '/api/v2/mcp/servers/${Uri.encodeComponent(name)}/test',
      method: 'POST',
    );
    return Map<String, dynamic>.from(value as Map);
  }

  Future<void> updateServer(String name, Map<String, dynamic> body) async {
    await client.requestJson(
      '/api/v2/mcp/servers/${Uri.encodeComponent(name)}',
      method: 'PUT',
      body: body,
    );
  }

  Future<void> deleteServer(String name) async {
    await client.requestJson(
      '/api/v2/mcp/servers/${Uri.encodeComponent(name)}',
      method: 'DELETE',
    );
  }
}
