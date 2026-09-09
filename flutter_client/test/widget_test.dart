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

void main() {
  testWidgets('login workbench is visible before authentication', (
    tester,
  ) async {
    await tester.pumpWidget(const ProviderScope(child: CodingMatrixApp()));

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
