import 'dart:convert';

import 'package:codingmatrix_desktop/infrastructure/agent/agent_stream_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/credential_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test(
    'sends the authenticated orchestration request and yields SSE chunks',
    () async {
      final store = CredentialStore();
      final tokenRef = store.storeAccessToken('secret-token');
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/agent/orchestrate/stream');
        expect(request.headers['authorization'], 'Bearer secret-token');
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['requirement'], 'build a dashboard');
        expect(body['enable_validation'], true);
        expect(body['api_key_token'], 'provider-token');
        expect(body['provider_id'], 'siliconflow');
        return http.Response(
          'data: {"type":"progress","data":{"progress":10}}\n\n'
          'data: {"type":"done","data":{}}\n\n',
          200,
          headers: {'content-type': 'text/event-stream'},
        );
      });
      final streamClient = AgentStreamClient(
        baseUrl: 'http://127.0.0.1:8080',
        httpClient: client,
        credentialStore: store,
      );

      final chunks = await streamClient
          .generate(
            accessTokenRef: tokenRef,
            requirement: 'build a dashboard',
            apiKeyToken: 'provider-token',
            providerId: 'siliconflow',
          )
          .toList();

      expect(chunks.join(), contains('"type":"done"'));
    },
  );

  test('rejects a missing credential before opening the request', () async {
    final streamClient = AgentStreamClient(
      baseUrl: 'http://127.0.0.1:8080',
      httpClient: MockClient((_) async => http.Response('', 500)),
      credentialStore: CredentialStore(),
    );

    await expectLater(
      streamClient
          .generate(accessTokenRef: 'missing', requirement: 'build a dashboard')
          .toList(),
      throwsA(isA<AgentStreamException>()),
    );
  });

  test('stops the authenticated backend session', () async {
    final store = CredentialStore();
    final tokenRef = store.storeAccessToken('secret-token');
    final client = MockClient((request) async {
      expect(request.method, 'POST');
      expect(request.url.path, '/api/v1/agent/stop/desktop-session');
      expect(request.headers['authorization'], 'Bearer secret-token');
      return http.Response('{}', 200);
    });
    final streamClient = AgentStreamClient(
      baseUrl: 'http://127.0.0.1:8080',
      httpClient: client,
      credentialStore: store,
    );

    await streamClient.stop(
      accessTokenRef: tokenRef,
      sessionId: 'desktop-session',
    );
  });
}
