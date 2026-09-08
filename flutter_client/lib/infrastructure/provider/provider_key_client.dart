import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:pointycastle/export.dart';
import 'package:pointycastle/asn1.dart';

import '../../domain/models/provider_key.dart';
import '../auth/authenticated_client.dart';

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
    final encrypted = _encrypt(key, await publicKey());
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

  String _encrypt(String value, String pem) {
    final der = base64Decode(
      pem
          .split('\n')
          .where((line) => !line.startsWith('-----'))
          .join()
          .replaceAll(RegExp(r'\s'), ''),
    );
    final spki = ASN1Parser(der).nextObject() as ASN1Sequence;
    final bits = spki.elements![1] as ASN1BitString;
    final rsa =
        ASN1Parser(Uint8List.fromList(bits.stringValues!)).nextObject()
            as ASN1Sequence;
    final key = RSAPublicKey(
      (rsa.elements![0] as ASN1Integer).integer!,
      (rsa.elements![1] as ASN1Integer).integer!,
    );
    final random = Random.secure();
    final cipher = OAEPEncoding.withSHA256(RSAEngine())
      ..init(
        true,
        ParametersWithRandom(
          PublicKeyParameter<RSAPublicKey>(key),
          FortunaRandom()..seed(
            KeyParameter(
              Uint8List.fromList(
                List<int>.generate(32, (_) => random.nextInt(256)),
              ),
            ),
          ),
        ),
      );
    final encrypted = cipher.process(Uint8List.fromList(utf8.encode(value)));
    return base64Encode(encrypted);
  }
}
