import 'dart:convert';
import 'dart:io';

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

  test('sends the incremental engine and project path', () async {
    final store = CredentialStore();
    final tokenRef = store.storeAccessToken('secret-token');
    final client = MockClient((request) async {
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      expect(body['incremental'], true);
      expect(body['engine'], 'core');
      expect(body['project_path'], '1/1789218793436');
      expect(body['is_resume'], false);
      return http.Response(
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

    await streamClient
        .generate(
          accessTokenRef: tokenRef,
          requirement: 'add a logout button',
          incremental: true,
          engine: 'core',
          projectPath: '1/1789218793436',
        )
        .toList();
  });

  test('omits the incremental fields for a fresh run', () async {
    final store = CredentialStore();
    final tokenRef = store.storeAccessToken('secret-token');
    final client = MockClient((request) async {
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      expect(body['incremental'], false);
      expect(body.containsKey('engine'), isFalse);
      expect(body.containsKey('project_path'), isFalse);
      return http.Response(
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

    await streamClient
        .generate(accessTokenRef: tokenRef, requirement: 'build a dashboard')
        .toList();
  });

  test('generate 网络断开向上抛出', () async {
    final store = CredentialStore();
    final tokenRef = store.storeAccessToken('secret-token');
    final streamClient = AgentStreamClient(
      baseUrl: 'http://127.0.0.1:8080',
      httpClient: MockClient(
        (_) async => throw const SocketException('connection lost'),
      ),
      credentialStore: store,
    );

    await expectLater(
      streamClient
          .generate(accessTokenRef: tokenRef, requirement: 'build a dashboard')
          .toList(),
      throwsA(
        isA<SocketException>().having(
          (error) => error.message,
          'message',
          'connection lost',
        ),
      ),
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

  test('stop 网络断开向上抛出', () async {
    final store = CredentialStore();
    final tokenRef = store.storeAccessToken('secret-token');
    final streamClient = AgentStreamClient(
      baseUrl: 'http://127.0.0.1:8080',
      httpClient: MockClient(
        (_) async => throw const SocketException('connection lost'),
      ),
      credentialStore: store,
    );

    await expectLater(
      streamClient.stop(accessTokenRef: tokenRef, sessionId: 'desktop-session'),
      throwsA(
        isA<SocketException>().having(
          (error) => error.message,
          'message',
          'connection lost',
        ),
      ),
    );
  });
}
