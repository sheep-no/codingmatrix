import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:codingmatrix_desktop/application/workbench_controller.dart';
import 'package:codingmatrix_desktop/domain/models/unified_models.dart';
import 'package:codingmatrix_desktop/infrastructure/agent/agent_project_client.dart';
import 'package:codingmatrix_desktop/infrastructure/agent/agent_stream_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/authenticated_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/cloud_auth_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/credential_store.dart';
import 'package:codingmatrix_desktop/presentation/agent_decision_page.dart';
import 'package:codingmatrix_desktop/presentation/project_files_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class DeliveryApi extends AuthenticatedClient {
  DeliveryApi(this.handle, {this.stream})
    : super(
        CloudAuthClient(
          baseUrl: 'https://example.com',
          httpClient: http.Client(),
          credentialStore: CredentialStore(),
        ),
        http.Client(),
      );
  final Future<Object?> Function(String, String, Object?) handle;
  final Stream<List<int>>? stream;
  @override
  Future<Object?> requestJson(
    String path, {
    String method = 'GET',
    Object? body,
  }) => handle(path, method, body);
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async =>
      http.StreamedResponse(
        stream ?? Stream.value([0x50, 0x4b, 5, 6, ...List.filled(18, 0)]),
        200,
      );
}

String event(String type, Map<String, dynamic> data) =>
    'data: ${jsonEncode({'type': type, 'data': data})}\n\n';
final question = {
  'id': 'database_choice',
  'question': '数据库选型',
  'context': '持久化',
  'options': [
    {'label': 'SQLite', 'description': '单机'},
    {'label': 'PostgreSQL', 'description': '服务端'},
  ],
  'default': 'SQLite',
};

void main() {
  test('late decision response cannot overwrite a new task', () async {
    final pending = Completer<Object?>();
    final controller = WorkbenchController(
      projectClient: AgentProjectClient(
        DeliveryApi((_, __, ___) => pending.future),
      ),
    );
    controller.bindTask(
      const Task(taskId: 'old', sessionId: 'old-session', status: 'running'),
    );
    controller.ingestSseChunk(
      event('critical_decisions', {
        'decisions': [question],
      }),
    );
    final submit = controller.submitDecisions({'database_choice': 'SQLite'});
    await controller.disconnect();
    controller.resetStream();
    controller.bindTask(const Task(taskId: 'new', status: 'running'));
    pending.complete({'status': 'submitted'});
    await submit;
    expect(controller.state.task?.taskId, 'new');
    expect(controller.state.decisionBusy, false);
    expect(controller.state.decisions, isEmpty);
    controller.dispose();
  });
  test(
    'decisions submit labels and terminal events keep their final state',
    () async {
      final controller = WorkbenchController(
        projectClient: AgentProjectClient(
          DeliveryApi((path, method, body) async {
            expect(path, '/api/v1/agent/session/s1/decision');
            expect(method, 'POST');
            expect(body, {'database_choice': 'SQLite'});
            return {'status': 'submitted'};
          }),
        ),
      );
      controller.bindTask(
        const Task(taskId: 't1', sessionId: 's1', status: 'running'),
      );
      controller.ingestSseChunk(
        event('critical_decisions', {
          'session_id': 's1',
          'decisions': [question],
        }),
      );
      expect(controller.state.task?.status, 'awaitingDecision');
      await controller.submitDecisions({'database_choice': 'SQLite'});
      expect(controller.state.decisions, isEmpty);
      controller.ingestSseChunk(event('done', {'project_path': '42/project'}));
      controller.ingestSseChunk(event('progress', {'progress': 3}));
      expect(controller.state.task?.status, 'success');
      expect(controller.state.projectPath, '42/project');
      controller.resetStream();
      expect(controller.state.projectPath, isNull);
      expect(controller.state.artifacts, isEmpty);
      controller.dispose();
    },
  );

  test('ignored decisions remain actionable with a visible error', () async {
    final controller = WorkbenchController(
      projectClient: AgentProjectClient(
        DeliveryApi((_, __, ___) async => {'status': 'ignored'}),
      ),
    );
    controller.bindTask(
      const Task(taskId: 't', sessionId: 's', status: 'running'),
    );
    controller.ingestSseChunk(
      event('critical_decisions', {
        'decisions': [question],
      }),
    );
    await controller.submitDecisions({'database_choice': 'SQLite'});
    expect(controller.state.actionError, isNotNull);
    expect(controller.state.decisions, hasLength(1));
    expect(controller.state.decisionBusy, false);
    controller.dispose();
  });

  test('file list/read preserve project and file query parameters', () async {
    final client = AgentProjectClient(
      DeliveryApi((path, method, body) async {
        final uri = Uri.parse(path);
        expect(uri.queryParameters['project_path'], '42/project name');
        if (uri.path.endsWith('/files')) {
          return {
            'files': [
              {'path': 'src/main.dart'},
            ],
          };
        }
        expect(uri.queryParameters['file_path'], 'src/a b.dart');
        return {'content': 'void main() {}'};
      }),
    );
    expect(await client.files('42/project name'), ['src/main.dart']);
    expect(
      await client.read('42/project name', 'src/a b.dart'),
      'void main() {}',
    );
  });

  test('ZIP download streams to disk and reports only complete file', () async {
    final directory = await Directory.systemTemp.createTemp('delivery-test-');
    final client = AgentProjectClient(
      DeliveryApi((_, __, ___) async => {}),
      directory: () async => directory,
    );
    var bytes = 0;
    final path = await client.download('42/project', (value) => bytes = value);
    expect(path.endsWith('.zip'), true);
    expect(await File(path).length(), bytes);
    expect(bytes, 22);
  });

  test('interrupted download never produces a completed ZIP', () async {
    final directory = await Directory.systemTemp.createTemp(
      'delivery-failure-',
    );
    Stream<List<int>> interrupted() async* {
      yield [0x50, 0x4b, 3, 4];
      throw const SocketException('connection lost');
    }

    final client = AgentProjectClient(
      DeliveryApi((_, __, ___) async => {}, stream: interrupted()),
      directory: () async => directory,
    );
    await expectLater(
      client.download('42/project', (_) {}),
      throwsA(isA<SocketException>()),
    );
    expect(
      await directory
          .list()
          .where((file) => file.path.endsWith('.zip'))
          .isEmpty,
      true,
    );
  });

  test('disconnect is distinct from business failure', () async {
    final store = CredentialStore();
    final token = store.storeAccessToken('test-access');
    final controller = WorkbenchController(
      streamClient: AgentStreamClient(
        baseUrl: 'https://example.com',
        httpClient: MockClient((_) async => http.Response('', 200)),
        credentialStore: store,
      ),
    );
    await controller.startGeneration(
      accessTokenRef: token,
      requirement: 'project',
    );
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(controller.state.task?.status, 'disconnected');
    controller.dispose();
  });

  testWidgets('decision page submits defaults and removes accepted form', (
    tester,
  ) async {
    final controller = WorkbenchController(
      projectClient: AgentProjectClient(
        DeliveryApi((_, __, body) async {
          expect(body, {'database_choice': 'SQLite'});
          return {'status': 'submitted'};
        }),
      ),
    );
    controller.bindTask(
      const Task(taskId: 't', sessionId: 's', status: 'running'),
    );
    controller.ingestSseChunk(
      event('critical_decisions', {
        'decisions': [question],
      }),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          workbenchControllerProvider.overrideWith((_) => controller),
        ],
        child: const MaterialApp(home: AgentDecisionPage()),
      ),
    );
    await tester.tap(find.text('提交决策'));
    await tester.pumpAndSettle();
    expect(find.text('提交决策'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('file tree expands and opens a selectable preview', (
    tester,
  ) async {
    final client = AgentProjectClient(
      DeliveryApi(
        (path, _, __) async => Uri.parse(path).path.endsWith('/files')
            ? {
                'files': [
                  {'path': 'src/main.dart'},
                ],
              }
            : {'content': 'void main() {}'},
      ),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [agentProjectClientProvider.overrideWithValue(client)],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('src'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('main.dart'));
    await tester.pumpAndSettle();
    expect(find.text('void main() {}'), findsOneWidget);
  });
}
