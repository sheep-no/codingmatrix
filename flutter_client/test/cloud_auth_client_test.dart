import 'package:codingmatrix_desktop/infrastructure/auth/cloud_auth_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/credential_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('login uses CSRF double submit and stores token by reference', () async {
    final store = CredentialStore();
    final seen = <http.Request>[];
    final client = MockClient((request) async {
      seen.add(request);
      if (request.method == 'GET' &&
          request.url.path == '/api/v1/auth/csrf-token') {
        return http.Response(
          '{"csrf_token":"csrf-abc","expires_in":3600}',
          200,
          headers: {
            'set-cookie': 'csrf_token=csrf-abc; Path=/; Max-Age=3600',
            'content-type': 'application/json',
          },
        );
      }
      if (request.method == 'POST' &&
          request.url.path == '/api/v1/auth/login') {
        expect(request.headers['x-csrf-token'], 'csrf-abc');
        expect(request.headers['cookie'], contains('csrf_token=csrf-abc'));
        expect(request.body, contains('"email":"user@example.com"'));
        return http.Response(
          '{"access_token":"secret-token","token_type":"bearer","username":"alice","permission_level":"admin"}',
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('not found', 404);
    });

    final auth = CloudAuthClient(
      baseUrl: 'http://127.0.0.1:8080',
      httpClient: client,
      credentialStore: store,
    );

    final session = await auth.login(
      email: 'user@example.com',
      password: 'passw0rd',
    );

    expect(seen, hasLength(2));
    expect(session.username, 'alice');
    expect(session.permissionLevel, 'admin');
    expect(session.accessTokenRef, isNot('secret-token'));
    expect(session.toJson().containsKey('access_token'), isFalse);
    expect(store.read(session.accessTokenRef), 'secret-token');
  });

  test('login surfaces CSRF failures', () async {
    final client = MockClient((request) async {
      return http.Response('{"detail":"missing CSRF token"}', 403);
    });
    final auth = CloudAuthClient(
      baseUrl: 'http://127.0.0.1:8080',
      httpClient: client,
      credentialStore: CredentialStore(),
    );

    expect(
      () => auth.login(email: 'a@b.c', password: 'x'),
      throwsA(isA<CloudAuthException>()),
    );
  });
}
