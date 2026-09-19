import '../../domain/models/provider_key.dart';
import '../auth/authenticated_client.dart';
import 'rsa_encrypt.dart';

const supportedProviders = <String>[
  'siliconflow',
  'openai',
  'anthropic',
  'bailian',
  'glm',
  'deepseek',
];

class ProviderKeyClient {
  ProviderKeyClient(this.api);
  final AuthenticatedClient api;

  Future<String> publicKey() async {
    final data = await api.requestJson('/api/v1/agent/apikey/public-key');
    return (data as Map<String, dynamic>)['public_key'] as String;
  }

  Future<String> submit({
    required String key,
    required String provider,
    int ttl = 86400,
    String remark = '',
  }) async {
    if (!supportedProviders.contains(provider)) {
      throw StateError('不支持的 Provider');
    }
    final encrypted = encryptWithPublicKey(key, await publicKey());
    final data = await api.requestJson(
      '/api/v1/agent/apikey',
      method: 'POST',
      body: {
        'encrypted_key': encrypted,
        'provider': provider,
        'ttl': ttl,
        'remark': remark,
      },
    );
    return (data as Map<String, dynamic>)['token'] as String;
  }

  Future<List<ProviderKeySummary>> list() async {
    final data = await api.requestJson('/api/v1/agent/apikeys');
    return (data as List)
        .map(
          (item) => ProviderKeySummary.fromJson(
            Map<String, dynamic>.from(item as Map),
          ),
        )
        .toList();
  }

  Future<void> test(String token) async {
    final result = await api.requestJson(
      '/api/v1/agent/apikey/test',
      method: 'POST',
      body: {'token': token},
    );
    if ((result as Map)['success'] != true) throw StateError('Key 测试失败');
  }

  Future<void> setEnabled(String token, bool enabled) async {
    await api.requestJson(
      '/api/v1/agent/apikey/$token/enabled?enabled=$enabled',
      method: 'PUT',
    );
  }

  Future<void> delete(String token) async {
    await api.requestJson('/api/v1/agent/apikey/$token', method: 'DELETE');
  }
}
