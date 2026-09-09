import 'package:codingmatrix_desktop/app.dart';
import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/application/workbench_controller.dart';
import 'package:codingmatrix_desktop/domain/models/auth_session.dart';
import 'package:codingmatrix_desktop/domain/models/unified_models.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/cloud_auth_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/credential_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class ExitWorkbenchController extends WorkbenchController {
  int stops = 0;
  int disconnects = 0;

  @override
  Future<void> stopGeneration({bool markCancelled = true}) async {
    stops++;
  }

  @override
  Future<void> disconnect() async {
    disconnects++;
  }
}

void main() {
  testWidgets('stop requires explicit cleanup confirmation', (tester) async {
    final workbench = ExitWorkbenchController();
    workbench.bindTask(
      const Task(taskId: 'active', sessionId: 'session', status: 'running'),
    );
    final store = CredentialStore();
    final auth = AuthController(
      CloudAuthClient(
        baseUrl: 'https://example.com',
        httpClient: MockClient((_) async => http.Response('', 500)),
        credentialStore: store,
      ),
      store,
      session: const AuthSession(
        username: 'alice',
        permissionLevel: 'normal',
        accessTokenRef: 'ref',
      ),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authControllerProvider.overrideWith((_) => auth),
          workbenchControllerProvider.overrideWith((_) => workbench),
        ],
        child: const CodingMatrixApp(),
      ),
    );
    await tester.tap(find.byKey(const Key('stopGenerationButton')));
    await tester.pumpAndSettle();
    expect(workbench.stops, 0);
    await tester.tap(find.text('继续任务'));
    await tester.pumpAndSettle();
    expect(workbench.stops, 0);
    await tester.tap(find.byKey(const Key('stopGenerationButton')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('停止并清理'));
    await tester.pumpAndSettle();
    expect(workbench.stops, 1);
  });
  testWidgets('logout disconnects locally without destructive stop', (
    tester,
  ) async {
    final store = CredentialStore();
    final workbench = ExitWorkbenchController();
    workbench.bindTask(
      const Task(taskId: 'active', sessionId: 'session', status: 'running'),
    );
    final auth = AuthController(
      CloudAuthClient(
        baseUrl: 'https://one.example',
        httpClient: MockClient(
          (_) async => throw StateError('Logout must not send HTTP'),
        ),
        credentialStore: store,
      ),
      store,
      session: const AuthSession(
        username: 'alice',
        permissionLevel: 'normal',
        accessTokenRef: 'ref',
      ),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          credentialStoreProvider.overrideWithValue(store),
          authControllerProvider.overrideWith((_) => auth),
          workbenchControllerProvider.overrideWith((_) => workbench),
        ],
        child: const CodingMatrixApp(),
      ),
    );
    await tester.tap(find.byKey(const Key('logoutButton')));
    await tester.pumpAndSettle();
    expect(workbench.stops, 0);
    expect(workbench.disconnects, 1);
    expect(find.byKey(const Key('loginButton')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('login workbench is visible before authentication', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          credentialStoreProvider.overrideWithValue(CredentialStore()),
        ],
        child: const CodingMatrixApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('CodingMatrix Agent'), findsOneWidget);
    expect(find.byKey(const Key('loginButton')), findsOneWidget);
    expect(find.text('Agent Workbench'), findsNothing);
  });

  testWidgets('authenticated workbench renders session and SSE events', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authControllerProvider.overrideWith((ref) {
            return AuthController(
              CloudAuthClient(
                baseUrl: 'http://127.0.0.1:8080',
                httpClient: MockClient((_) async => http.Response('', 500)),
                credentialStore: CredentialStore(),
              ),
              CredentialStore(),
              session: const AuthSession(
                username: 'alice',
                permissionLevel: 'admin',
                accessTokenRef: 'token-1',
              ),
            );
          }),
          workbenchControllerProvider.overrideWith((ref) {
            final controller = WorkbenchController();
            controller.bindSession(
              const Session(id: 'sess-1', userId: 1, module: 'agent'),
            );
            controller.bindTask(
              const Task(taskId: 'task-1', status: 'running', progress: 10),
            );
            controller.ingestSseChunk(
              'data: {"type":"log","data":{"message":"started"}}\n\n',
            );
            return controller;
          }),
        ],
        child: const CodingMatrixApp(),
      ),
    );

    expect(find.text('工作台'), findsOneWidget);
    expect(find.text('alice'), findsOneWidget);
    expect(find.textContaining('sess-1'), findsOneWidget);
    expect(find.textContaining('log:'), findsOneWidget);
  });

  testWidgets('compact workbench handles short windows and long usernames', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(520, 360);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authControllerProvider.overrideWith((ref) {
            return AuthController(
              CloudAuthClient(
                baseUrl: 'http://127.0.0.1:8080',
                httpClient: MockClient((_) async => http.Response('', 500)),
                credentialStore: CredentialStore(),
              ),
              CredentialStore(),
              session: const AuthSession(
                username: 'a-very-long-windows-desktop-username@example.com',
                permissionLevel: 'admin',
                accessTokenRef: 'token-1',
              ),
            );
          }),
        ],
        child: const CodingMatrixApp(),
      ),
    );

    expect(tester.takeException(), isNull);
    expect(find.text('任务概览'), findsOneWidget);
    expect(find.text('实时事件'), findsOneWidget);
  });
}
