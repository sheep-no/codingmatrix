import 'dart:async';
import 'dart:convert';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/application/workbench_controller.dart';
import 'package:codingmatrix_desktop/domain/models/unified_models.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/authenticated_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/cloud_auth_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/credential_store.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/session_cookies.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class MemoryStorage implements SessionStorage {
  String? value;
  bool failWrite = false;
  bool failDelete = false;
  Completer<void>? writeGate;
  bool writing = false;
  @override
  Future<String?> read() async => value;
  @override
  Future<void> write(String value) async {
    if (failWrite) throw StateError('secret-storage-error');
    writing = true;
    await writeGate?.future;
    this.value = value;
  }

  @override
  Future<void> delete() async {
    if (failDelete) throw StateError('secret-storage-error');
    value = null;
  }
}

String token(String subject, {bool expired = false, int revision = 0}) {
  final exp = DateTime.now().add(Duration(hours: expired ? -1 : 1));
  return 'header.${base64Url.encode(utf8.encode(jsonEncode({'sub': subject, 'exp': exp.millisecondsSinceEpoch ~/ 1000, 'revision': revision}))).replaceAll('=', '')}.signature';
}

http.Response authResponse(String access, {bool login = true}) => http.Response(
  jsonEncode({
    'access_token': access,
    'username': 'alice',
    'csrf_token': 'rotated',
  }),
  200,
  headers: {
    'set-cookie':
        '${login ? 'refresh_token=refresh-secret; Path=/api/v1; HttpOnly; Secure; Max-Age=604800, ' : ''}'
        'csrf_token=rotated; Path=/; Secure; Max-Age=3600',
  },
);

class Fixture {
  Fixture({MemoryStorage? storage}) : storage = storage ?? MemoryStorage() {
    store = CredentialStore(storage: this.storage);
    transport = MockClient((request) async {
      requests.add(request);
      switch (request.url.path) {
        case '/api/v1/csrf-token':
          return http.Response(
            '{"csrf_token":"fresh"}',
            200,
            headers: {
              'set-cookie': 'csrf_token=fresh; Path=/; Secure; Max-Age=3600',
            },
          );
        case '/api/v1/login':
          return authResponse(token(subject, expired: expired));
        case '/api/v1/refresh':
          refreshes++;
          expect(
            request.headers['cookie'],
            contains('refresh_token=refresh-secret'),
          );
          expect(request.headers['cookie'], contains('csrf_token=fresh'));
          expect(request.headers['x-csrf-token'], 'fresh');
          if (refreshGate != null) return refreshGate!.future;
          if (refreshFails) return http.Response('secret-provider-key', 401);
          return authResponse(
            token(subject, revision: refreshes),
            login: false,
          );
        default:
          return await business?.call(request) ?? http.Response('{}', 200);
      }
    });
    auth = CloudAuthClient(
      baseUrl: 'https://one.example',
      httpClient: transport,
      credentialStore: store,
    );
    api = AuthenticatedClient(auth, transport);
  }
  final MemoryStorage storage;
  late final CredentialStore store;
  late final MockClient transport;
  late final CloudAuthClient auth;
  late final AuthenticatedClient api;
  final requests = <http.Request>[];
  int refreshes = 0;
  bool expired = false;
  bool refreshFails = false;
  String subject = '1';
  Completer<http.Response>? refreshGate;
  Future<http.Response> Function(http.Request)? business;

  Future<void> login({String? url}) async {
    await auth.login(
      email: 'alice@example.com',
      password: 'password-secret',
      serviceUrl: url,
    );
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'device storage adapter saves, restores and deletes only its session key',
    () async {
      FlutterSecureStorage.setMockInitialValues({'unrelated': 'keep'});
      const device = DeviceSessionStorage();
      final store = CredentialStore(storage: device);
      await store.saveSession({
        'version': 1,
        'access_token': 'test-only-secret',
      });
      final restarted = CredentialStore(storage: device);
      expect(
        (await restarted.loadSession())!['access_token'],
        'test-only-secret',
      );
      await restarted.clearSession();
      expect(await restarted.loadSession(), isNull);
      expect(await const FlutterSecureStorage().read(key: 'unrelated'), 'keep');
    },
  );

  test(
    'logout waits behind pending persistence and leaves no restorable session',
    () async {
      final f = Fixture();
      f.storage.writeGate = Completer<void>();
      final loggingIn = f.login();
      final failure = expectLater(
        loggingIn,
        throwsA(isA<CloudAuthException>()),
      );
      while (!f.storage.writing) {
        await Future<void>.delayed(Duration.zero);
      }
      final logout = f.auth.logout();
      f.storage.writeGate!.complete();
      await logout;
      await failure;
      expect(f.storage.value, isNull);
      expect(f.auth.session, isNull);
    },
  );

  test('a timed out authentication request returns a redacted error', () async {
    final gate = Completer<http.Response>();
    final auth = CloudAuthClient(
      baseUrl: 'https://one.example',
      httpClient: MockClient((_) => gate.future),
      credentialStore: CredentialStore(),
      timeout: const Duration(milliseconds: 10),
    );
    await expectLater(
      auth.login(email: 'alice@example.com', password: 'secret'),
      throwsA(
        predicate(
          (e) => e is CloudAuthException && !e.toString().contains('secret'),
        ),
      ),
    );
    gate.complete(http.Response('{}', 200));
    expect(auth.session, isNull);
  });

  test(
    'JSON errors and permission failures expose no response secrets',
    () async {
      final f = Fixture();
      await f.login();
      f.business = (_) async => http.Response('secret-private-response', 200);
      await expectLater(
        f.api.requestJson('/api/v1/data'),
        throwsA(
          predicate(
            (e) => e is CloudAuthException && !e.toString().contains('secret'),
          ),
        ),
      );
      f.business = (_) async => http.Response('secret-private-response', 403);
      await expectLater(
        f.api.requestJson('/api/v1/data'),
        throwsA(
          predicate(
            (e) =>
                e is CloudAuthException &&
                e.statusCode == 403 &&
                !e.toString().contains('secret'),
          ),
        ),
      );
      expect(f.refreshes, 0);
      expect(f.auth.session, isNotNull);
    },
  );

  test(
    'Riverpod resets account-bound workbench on logout and next login',
    () async {
      final f = Fixture();
      final container = ProviderContainer(
        overrides: [
          credentialStoreProvider.overrideWithValue(f.store),
          httpClientProvider.overrideWithValue(f.transport),
          cloudAuthClientProvider.overrideWithValue(f.auth),
        ],
      );
      addTearDown(container.dispose);
      final auth = container.read(authControllerProvider.notifier);
      await Future<void>.delayed(Duration.zero);
      await auth.login(email: 'alice@example.com', password: 'password-secret');
      final old = container.read(workbenchControllerProvider.notifier);
      old.bindSession(const Session(id: 'private', userId: 1, module: 'agent'));
      old.ingestSseChunk(
        'data: {"type":"log","data":{"message":"private"}}\n\n',
      );
      await auth.logout();
      expect(container.read(workbenchControllerProvider).session, isNull);
      expect(container.read(workbenchControllerProvider).events, isEmpty);
      expect(
        identical(container.read(workbenchControllerProvider.notifier), old),
        false,
      );
      f.subject = '2';
      await auth.login(
        email: 'bob@example.com',
        password: 'other',
        serviceUrl: 'https://two.example',
      );
      expect(container.read(workbenchControllerProvider).events, isEmpty);
    },
  );

  test(
    'refresh cannot replace the current account with another subject',
    () async {
      final f = Fixture();
      await f.login();
      f.subject = '2';
      await expectLater(f.auth.refresh(), throwsA(isA<CloudAuthException>()));
      expect(f.auth.session, isNull);
      expect(f.storage.value, isNull);
    },
  );

  test('failed local cleanup is visible and can be retried', () async {
    final f = Fixture();
    final controller = AuthController(f.auth, f.store);
    await controller.login(
      email: 'alice@example.com',
      password: 'password-secret',
    );
    f.storage.failDelete = true;
    await controller.logout();
    expect(controller.state.isAuthenticated, false);
    expect(controller.state.errorMessage, contains('清除失败'));
    expect(controller.state.errorMessage, isNot(contains('secret')));
    f.storage.failDelete = false;
    await controller.logout();
    expect(f.storage.value, isNull);
    expect(controller.state.errorMessage, isNull);
    controller.dispose();
  });

  test(
    'restarts from device record and verifies refresh before restoring account',
    () async {
      final first = Fixture();
      await first.login();
      final saved = jsonDecode(first.storage.value!) as Map;
      expect(saved['base_url'], 'https://one.example');
      expect(saved['account'], 'alice@example.com');
      expect(first.storage.value, isNot(contains('password-secret')));
      final restarted = Fixture(storage: first.storage);
      final controller = AuthController(restarted.auth, restarted.store);
      await controller.restore();
      expect(controller.state.isAuthenticated, true);
      expect(restarted.refreshes, 1);
      expect(restarted.auth.baseUrl, 'https://one.example');
      controller.dispose();
    },
  );

  test(
    'expired access token refreshes before the first business request',
    () async {
      final f = Fixture()..expired = true;
      await f.login();
      f.business = (request) async {
        expect(
          request.headers['authorization'],
          'Bearer ${token('1', revision: 1)}',
        );
        expect(request.headers['x-csrf-token'], 'rotated');
        return http.Response('{}', 200);
      };
      await f.api.get(Uri.parse('https://one.example/api/v1/data'));
      expect(f.refreshes, 1);
    },
  );

  test(
    'concurrent and delayed 401 responses share one refresh and one retry each',
    () async {
      final f = Fixture();
      await f.login();
      final oldToken = f.store.read(f.auth.session!.accessTokenRef)!;
      final bothArrived = Completer<void>();
      var arrivals = 0;
      f.business = (request) async {
        if (request.headers['authorization'] == 'Bearer $oldToken') {
          arrivals++;
          if (arrivals == 2) bothArrived.complete();
          await bothArrived.future;
          return http.Response('', 401);
        }
        return http.Response('{}', 200);
      };
      final responses = await Future.wait([
        f.api.get(Uri.parse('https://one.example/api/v1/a')),
        f.api.get(Uri.parse('https://one.example/api/v1/b')),
      ]);
      expect(responses.map((r) => r.statusCode), [200, 200]);
      expect(f.refreshes, 1);
      await f.auth.refresh(rejectedToken: oldToken);
      expect(f.refreshes, 1);
      expect(f.requests.where((r) => r.url.path == '/api/v1/a'), hasLength(2));
    },
  );

  for (final status in [401, 429, 503]) {
    test('generation mutation is never replayed after HTTP $status', () async {
      final f = Fixture();
      await f.login();
      f.business = (_) async => http.Response('secret-provider-key', status);
      final request = f.api.post(
        Uri.parse('https://one.example/api/v1/agent/orchestrate/stream'),
      );
      if (status == 401) {
        await expectLater(request, throwsA(isA<CloudAuthException>()));
        expect(f.refreshes, 1);
      } else {
        await expectLater(
          request,
          throwsA(
            predicate(
              (e) =>
                  e is CloudAuthException &&
                  e.statusCode == status &&
                  !e.toString().contains('secret'),
            ),
          ),
        );
      }
      expect(
        f.requests.where((r) => r.url.path.contains('/agent/')),
        hasLength(1),
      );
    });
  }

  test('network exception is redacted and mutation is not retried', () async {
    final f = Fixture();
    await f.login();
    f.business = (_) async =>
        throw Exception('Bearer secret-provider-key password-secret');
    await expectLater(
      f.api.post(
        Uri.parse('https://one.example/api/v1/agent/orchestrate/stream'),
      ),
      throwsA(
        predicate(
          (e) => e is CloudAuthException && !e.toString().contains('secret'),
        ),
      ),
    );
    expect(
      f.requests.where((r) => r.url.path.contains('/agent/')),
      hasLength(1),
    );
  });

  test(
    'refresh failure clears persisted credentials and returns controller to login',
    () async {
      final f = Fixture();
      final controller = AuthController(f.auth, f.store);
      await controller.login(
        email: 'alice@example.com',
        password: 'password-secret',
      );
      final ref = f.auth.session!.accessTokenRef;
      f.refreshFails = true;
      f.business = (_) async => http.Response('', 401);
      await expectLater(
        f.api.get(Uri.parse('https://one.example/api/v1/data')),
        throwsA(isA<CloudAuthException>()),
      );
      expect(f.storage.value, isNull);
      expect(f.store.read(ref), isNull);
      expect(controller.state.isAuthenticated, false);
      controller.dispose();
    },
  );

  test('a second 401 is not retried and clears authentication', () async {
    final f = Fixture();
    await f.login();
    f.business = (_) async => http.Response('', 401);
    await expectLater(
      f.api.get(Uri.parse('https://one.example/api/v1/data')),
      throwsA(isA<CloudAuthException>()),
    );
    expect(f.refreshes, 1);
    expect(f.auth.session, isNull);
    expect(f.requests.where((r) => r.url.path.endsWith('/data')), hasLength(2));
  });

  test(
    'service switch and account switch discard previous cookies and references',
    () async {
      final f = Fixture();
      await f.login();
      final oldRef = f.auth.session!.accessTokenRef;
      f.subject = '2';
      await f.auth.login(
        email: 'bob@example.com',
        password: 'other',
        serviceUrl: 'https://two.example/',
      );
      expect(f.store.read(oldRef), isNull);
      final sent = f.requests
          .where((r) => r.url.host == 'two.example')
          .toList();
      expect(sent.first.headers['cookie'], isEmpty);
      expect(sent.last.headers['cookie'], isNot(contains('refresh-secret')));
      expect(jsonDecode(f.storage.value!)['account'], 'bob@example.com');
      await expectLater(
        f.api.get(Uri.parse('https://one.example/api/v1/data')),
        throwsA(isA<CloudAuthException>()),
      );
      expect(f.requests.where((r) => r.url.path.endsWith('/data')), isEmpty);
      final secondRef = f.auth.session!.accessTokenRef;
      f.subject = '3';
      await f.auth.login(email: 'carol@example.com', password: 'other');
      expect(f.store.read(secondRef), isNull);
      expect(
        f.requests.last.headers['cookie'],
        isNot(contains('refresh-secret')),
      );
    },
  );

  test(
    'logout during refresh fences late response and never calls backend logout',
    () async {
      final f = Fixture();
      await f.login();
      f.refreshGate = Completer<http.Response>();
      final refreshing = f.auth.refresh();
      final failure = expectLater(
        refreshing,
        throwsA(isA<CloudAuthException>()),
      );
      while (f.refreshes == 0) {
        await Future<void>.delayed(Duration.zero);
      }
      await f.auth.logout();
      f.refreshGate!.complete(
        authResponse(token('1', revision: 1), login: false),
      );
      await failure;
      expect(f.auth.session, isNull);
      expect(f.storage.value, isNull);
      expect(f.requests.any((r) => r.url.path.contains('logout')), false);
    },
  );

  test(
    'corrupt persistence is removed and restore exposes a safe error',
    () async {
      final f = Fixture();
      f.storage.value = 'secret-invalid-json';
      final controller = AuthController(f.auth, f.store);
      await controller.restore();
      expect(controller.state.isAuthenticated, false);
      expect(controller.state.errorMessage, isNot(contains('secret')));
      expect(f.storage.value, isNull);
      controller.dispose();
    },
  );

  test(
    'storage failure fails login closed without disclosing platform error',
    () async {
      final f = Fixture();
      f.storage.failWrite = true;
      final controller = AuthController(f.auth, f.store);
      await controller.login(
        email: 'alice@example.com',
        password: 'password-secret',
      );
      expect(controller.state.isAuthenticated, false);
      expect(controller.state.errorMessage, isNot(contains('secret')));
      expect(f.auth.session, isNull);
      controller.dispose();
    },
  );

  test(
    'cookies merge Expires commas, preserve refresh, and enforce scope and expiry',
    () {
      final origin = Uri.parse('https://one.example');
      final jar = SessionCookies(origin);
      final now = DateTime.utc(2026, 9, 8);
      jar.merge(
        'refresh_token=r; Path=/api/v1; Secure; Expires=Wed, 09 Sep 2026 10:00:00 GMT, csrf_token=c; Path=/; Max-Age=60',
        origin,
        now: now,
      );
      jar.merge('csrf_token=new; Path=/; Max-Age=60', origin, now: now);
      expect(
        jar.header(Uri.parse('https://one.example/api/v1/data'), now: now),
        'refresh_token=r; csrf_token=new',
      );
      expect(
        jar.header(Uri.parse('https://one.example/api/v10'), now: now),
        'csrf_token=new',
      );
      expect(
        jar.header(Uri.parse('https://other.example/api/v1'), now: now),
        isEmpty,
      );
      expect(
        jar.header(Uri.parse('http://one.example/api/v1'), now: now),
        isEmpty,
      );
      jar.merge('csrf_token=foreign; Domain=example; Path=/', origin, now: now);
      expect(jar.header(origin, now: now), isNot(contains('foreign')));
      expect(
        jar.header(
          Uri.parse('https://one.example/api/v1'),
          now: now.add(const Duration(minutes: 2)),
        ),
        'refresh_token=r',
      );
      jar.merge(
        'refresh_token=gone; Path=/api/v1; Max-Age=0',
        origin,
        now: now,
      );
      expect(
        jar.header(Uri.parse('https://one.example/api/v1'), now: now),
        isNot(contains('refresh_token')),
      );
    },
  );

  test(
    'secure cookies from HTTP are rejected and invalid service URLs are rejected',
    () {
      final origin = Uri.parse('http://one.example');
      final jar = SessionCookies(origin)
        ..merge('refresh_token=r; Secure; Path=/', origin);
      expect(jar.header(origin), isEmpty);
      for (final url in [
        'file:///tmp',
        'https://user:pass@one.example',
        'https://one.example/path',
        'https://one.example?token=x',
      ]) {
        expect(
          () => CloudAuthClient.normalizeBaseUrl(url),
          throwsA(isA<CloudAuthException>()),
        );
      }
    },
  );
}
