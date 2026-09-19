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

import 'dart:convert';
import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/infrastructure/agent/agent_stream_client.dart';
import 'package:codingmatrix_desktop/presentation/workbench_page.dart';
import 'auth_session_test.dart' show Fixture;
import 'module_lifecycle_test.dart' show ModuleAuth;

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

class StopErrorWorkbench extends WorkbenchController {
  StopErrorWorkbench() {
    state = const WorkbenchState(
      task: Task(
        taskId: 'local-1',
        sessionId: 'desktop-1',
        status: 'disconnected',
      ),
      actionError: '停止结果未确认，请重试或检查服务端任务',
    );
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

  AuthController signedInAuth(CredentialStore store, String tokenRef) {
    return AuthController(
      CloudAuthClient(
        baseUrl: 'https://example.com',
        httpClient: MockClient((_) async => http.Response('', 500)),
        credentialStore: store,
      ),
      store,
      session: AuthSession(
        username: 'alice',
        permissionLevel: 'normal',
        accessTokenRef: tokenRef,
      ),
    );
  }

  testWidgets('切换账号清空工作台需求草稿', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final container = ProviderContainer(
      overrides: [authControllerProvider.overrideWith((_) => auth)],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: WorkbenchPage()),
      ),
    );
    await tester.pump();
    await tester.enterText(
      find.byKey(const Key('requirementField')),
      '上一账号的需求',
    );
    expect(
      tester
          .widget<TextField>(find.byKey(const Key('requirementField')))
          .controller
          ?.text,
      '上一账号的需求',
    );

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    expect(
      tester
          .widget<TextField>(find.byKey(const Key('requirementField')))
          .controller
          ?.text,
      isEmpty,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('空需求不会开始生成', (tester) async {
    final store = CredentialStore();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authControllerProvider.overrideWith(
            (_) => signedInAuth(store, 'ref'),
          ),
        ],
        child: const MaterialApp(home: WorkbenchPage()),
      ),
    );
    await tester.pump();
    await tester.tap(find.byKey(const Key('startGenerationButton')));
    await tester.pump();
    expect(find.byKey(const Key('startGenerationButton')), findsOneWidget);
    expect(find.text('连接已断开，服务端任务状态待确认。可在「会话历史」中选择该会话恢复连接。'), findsNothing);
  });

  testWidgets('事件流断开显示待确认不泄露连接细节', (tester) async {
    final store = CredentialStore();
    final token = store.storeAccessToken('test-access');
    final workbench = WorkbenchController(
      streamClient: AgentStreamClient(
        baseUrl: 'https://example.com',
        httpClient: MockClient(
          (_) async => throw const SocketException('connection lost'),
        ),
        credentialStore: store,
      ),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authControllerProvider.overrideWith(
            (_) => signedInAuth(store, token),
          ),
          workbenchControllerProvider.overrideWith((_) => workbench),
        ],
        child: const MaterialApp(home: WorkbenchPage()),
      ),
    );
    await tester.enterText(find.byKey(const Key('requirementField')), '做一个应用');
    await tester.tap(find.byKey(const Key('startGenerationButton')));
    await tester.pump();
    await tester.pump();
    expect(find.text('连接已断开，服务端任务状态待确认。可在「会话历史」中选择该会话恢复连接。'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('disconnected'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('生成中退出再进入会丢掉输入但保留断开状态', (tester) async {
    final store = CredentialStore();
    final token = store.storeAccessToken('test-access');
    final pending = Completer<http.Response>();
    final workbench = WorkbenchController(
      streamClient: AgentStreamClient(
        baseUrl: 'https://example.com',
        httpClient: MockClient((_) => pending.future),
        credentialStore: store,
      ),
    );
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => signedInAuth(store, token)),
        workbenchControllerProvider.overrideWith((_) => workbench),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: WorkbenchPage()),
      ),
    );
    await tester.enterText(find.byKey(const Key('requirementField')), '做一个应用');
    await tester.tap(find.byKey(const Key('startGenerationButton')));
    await tester.pump();
    await tester.pump();
    expect(find.byKey(const Key('stopGenerationButton')), findsOneWidget);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: SizedBox.shrink()),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: WorkbenchPage()),
      ),
    );
    await tester.pump();
    expect(find.text('连接已断开，服务端任务状态待确认。可在「会话历史」中选择该会话恢复连接。'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(
      tester
          .widget<TextField>(find.byKey(const Key('requirementField')))
          .controller
          ?.text,
      isEmpty,
    );
  });

  test('停止网络断开显示笼统错误', () async {
    final store = CredentialStore();
    final token = store.storeAccessToken('test-access');
    var stopCalls = 0;
    final workbench = WorkbenchController(
      streamClient: AgentStreamClient(
        baseUrl: 'https://example.com',
        httpClient: MockClient((request) async {
          if (request.url.path.contains('/agent/stop/')) {
            stopCalls++;
            throw const SocketException('connection lost');
          }
          return http.Response('', 200);
        }),
        credentialStore: store,
      ),
    );
    await workbench.startGeneration(
      accessTokenRef: token,
      requirement: '做一个应用',
    );
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    await workbench.stopGeneration();
    expect(stopCalls, 1);
    expect(workbench.state.actionError, '停止结果未确认，请重试或检查服务端任务');
    expect(workbench.state.task?.status, 'disconnected');
    workbench.dispose();
  });

  testWidgets('停止失败后退出再进入仍显示错误', (tester) async {
    final store = CredentialStore();
    final workbench = StopErrorWorkbench();
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => signedInAuth(store, 'ref')),
        workbenchControllerProvider.overrideWith((_) => workbench),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: WorkbenchPage()),
      ),
    );
    await tester.pump();
    expect(find.text('停止结果未确认，请重试或检查服务端任务'), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开工作台'))),
      ),
    );
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: WorkbenchPage()),
      ),
    );
    await tester.pump();
    expect(find.text('停止结果未确认，请重试或检查服务端任务'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(
      tester
          .widget<TextField>(find.byKey(const Key('requirementField')))
          .controller
          ?.text,
      isEmpty,
    );
    expect(tester.takeException(), isNull);
  });

  test('停止时取消订阅抛错不会逃逸', () async {
    final store = CredentialStore();
    final token = store.storeAccessToken('test-access');
    final source = StreamController<List<int>>(
      onCancel: () async => throw const SocketException('connection lost'),
    );
    addTearDown(() {
      unawaited(source.close());
    });
    final workbench = WorkbenchController(
      streamClient: AgentStreamClient(
        baseUrl: 'https://example.com',
        httpClient: MockClient.streaming(
          (request, _) async => request.url.path.contains('/agent/stop/')
              ? http.StreamedResponse(const Stream<List<int>>.empty(), 200)
              : http.StreamedResponse(source.stream, 200),
        ),
        credentialStore: store,
      ),
    );
    await workbench.startGeneration(
      accessTokenRef: token,
      requirement: '做一个应用',
    );
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    await workbench.stopGeneration();
    expect(workbench.state.task?.status, 'cancelled');
    workbench.dispose();
  });

  test('心跳帧不进入事件日志', () async {
    final store = CredentialStore();
    final token = store.storeAccessToken('test-access');
    final source = StreamController<List<int>>();
    addTearDown(() {
      unawaited(source.close());
    });
    final workbench = WorkbenchController(
      streamClient: AgentStreamClient(
        baseUrl: 'https://example.com',
        httpClient: MockClient.streaming(
          (_, __) async => http.StreamedResponse(source.stream, 200),
        ),
        credentialStore: store,
      ),
    );
    await workbench.startGeneration(
      accessTokenRef: token,
      requirement: '做一个应用',
    );
    await Future<void>.delayed(Duration.zero);
    source.add(utf8.encode('data: {"type": "heartbeat"}\n\n'));
    source.add(
      utf8.encode('data: {"type": "progress", "data": {"progress": 10}}\n\n'),
    );
    source.add(utf8.encode('data: {"type": "heartbeat"}\n\n'));
    await Future<void>.delayed(Duration.zero);
    expect(workbench.state.events.map((event) => event.type).toList(), [
      'progress',
    ]);
    expect(workbench.state.task?.progress, 10);
    workbench.dispose();
  });

  test('Agent 事件日志只保留最近 100 条', () {
    final workbench = WorkbenchController();
    workbench.bindTask(const Task(taskId: 'task-1', status: 'running'));
    for (var i = 0; i < 150; i++) {
      workbench.ingestSseChunk(
        'data: {"type":"log","data":{"message":"$i"}}\n\n',
      );
    }
    final messages = workbench.state.events
        .map((event) => event.data?['message'])
        .toList();
    expect(messages.length, 100);
    expect(messages.first, '50');
    expect(messages.last, '149');
    workbench.dispose();
  });

  test('断开时取消订阅抛错不会逃逸', () async {
    final store = CredentialStore();
    final token = store.storeAccessToken('test-access');
    final source = StreamController<List<int>>(
      onCancel: () async => throw const SocketException('connection lost'),
    );
    addTearDown(() {
      unawaited(source.close());
    });
    final workbench = WorkbenchController(
      streamClient: AgentStreamClient(
        baseUrl: 'https://example.com',
        httpClient: MockClient.streaming(
          (_, __) async => http.StreamedResponse(source.stream, 200),
        ),
        credentialStore: store,
      ),
    );
    await workbench.startGeneration(
      accessTokenRef: token,
      requirement: '做一个应用',
    );
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    await workbench.disconnect();
    expect(workbench.state.task?.status, 'running');
    workbench.dispose();
  });
}
