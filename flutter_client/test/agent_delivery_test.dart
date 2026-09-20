import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:codingmatrix_desktop/application/workbench_controller.dart';
import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/domain/models/unified_models.dart';
import 'package:codingmatrix_desktop/infrastructure/agent/agent_project_client.dart';
import 'package:codingmatrix_desktop/infrastructure/agent/agent_stream_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/authenticated_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/cloud_auth_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/credential_store.dart';
import 'package:codingmatrix_desktop/presentation/agent_decision_page.dart';
import 'package:codingmatrix_desktop/presentation/github_settings_page.dart';
import 'package:codingmatrix_desktop/presentation/project_files_page.dart';
import 'package:codingmatrix_desktop/application/github_controller.dart';
import 'package:codingmatrix_desktop/infrastructure/github/github_client.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'auth_session_test.dart' show Fixture;
import 'module_lifecycle_test.dart' show ModuleAuth;

class DeliveryApi extends AuthenticatedClient {
  DeliveryApi(this.handle, {this.stream, this.sendHandle})
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
  final Future<http.StreamedResponse> Function(http.BaseRequest)? sendHandle;
  @override
  Future<Object?> requestJson(
    String path, {
    String method = 'GET',
    Object? body,
    Duration? timeout,
  }) => handle(path, method, body);
  @override
  Future<String> requestText(String path) async {
    final result = await handle(path, 'GET', null);
    if (result is String) return result;
    throw StateError('requestText expected a String for $path');
  }

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    if (sendHandle != null) return sendHandle!(request);
    return Future.value(
      http.StreamedResponse(
        stream ?? Stream.value([0x50, 0x4b, 5, 6, ...List.filled(18, 0)]),
        200,
      ),
    );
  }
}

class _ScriptedDownloadClient extends AgentProjectClient {
  _ScriptedDownloadClient(this.script)
    : super(
        DeliveryApi(
          (path, _, __) async => Uri.parse(path).path.endsWith('/files')
              ? {
                  'files': [
                    {'path': 'README.md'},
                  ],
                }
              : {'content': '# demo'},
        ),
      );
  final Future<String> Function() script;
  @override
  Future<String> download(
    String project,
    void Function(int) progress, {
    bool Function()? active,
  }) => script();
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

  testWidgets('没有待决策时不显示提交按钮', (tester) async {
    final controller = WorkbenchController(
      projectClient: AgentProjectClient(
        DeliveryApi((_, __, ___) async => {'status': 'submitted'}),
      ),
    );
    controller.bindTask(
      const Task(taskId: 't', sessionId: 's', status: 'running'),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          workbenchControllerProvider.overrideWith((_) => controller),
        ],
        child: const MaterialApp(home: AgentDecisionPage()),
      ),
    );
    expect(find.text('当前没有待提交的决策，请返回工作台查看进度。'), findsOneWidget);
    expect(find.text('提交决策'), findsNothing);
  });

  testWidgets('默认值不在可选项内时仍能渲染并要求显式选择', (tester) async {
    // The shipped `state_management` template announces default "Pinia" while
    // its options only offer "Pinia/Vuex"; a dropdown value outside its items
    // hits a Flutter assertion, so the page must not trust the default.
    var submissions = 0;
    final controller = WorkbenchController(
      projectClient: AgentProjectClient(
        DeliveryApi((_, __, ___) async {
          submissions++;
          return {'status': 'submitted'};
        }),
      ),
    );
    controller.bindTask(
      const Task(taskId: 't', sessionId: 's', status: 'running'),
    );
    controller.ingestSseChunk(
      event('critical_decisions', {
        'decisions': [
          {
            'id': 'state_management',
            'question': '状态管理方案',
            'context': '复杂应用的状态管理方式。',
            'options': [
              {'label': 'Pinia/Vuex', 'description': '集中式状态管理'},
              {'label': 'Redux', 'description': '严格单向数据流'},
            ],
            'default': 'Pinia',
          },
        ],
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
    expect(tester.takeException(), isNull);
    expect(find.text('Pinia'), findsNothing);

    await tester.tap(find.text('提交决策'));
    await tester.pumpAndSettle();
    expect(submissions, 0);
    expect(find.text('请为每个决策选择有效选项'), findsOneWidget);
  });

  testWidgets('提交决策网络断开显示笼统错误', (tester) async {
    final controller = WorkbenchController(
      projectClient: AgentProjectClient(
        DeliveryApi(
          (_, __, ___) async => throw const SocketException('connection lost'),
        ),
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
    await tester.pump();
    await tester.pump();
    expect(find.text('决策未被确认，等待可能已超时；请查看任务进度'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('提交决策'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('提交决策失败后退出再进入仍显示错误', (tester) async {
    final controller = WorkbenchController(
      projectClient: AgentProjectClient(
        DeliveryApi(
          (_, __, ___) async => throw const SocketException('connection lost'),
        ),
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
    final container = ProviderContainer(
      overrides: [workbenchControllerProvider.overrideWith((_) => controller)],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentDecisionPage()),
      ),
    );
    await tester.tap(find.text('提交决策'));
    await tester.pump();
    await tester.pump();
    expect(find.text('决策未被确认，等待可能已超时；请查看任务进度'), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开决策'))),
      ),
    );
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentDecisionPage()),
      ),
    );
    await tester.pump();
    expect(find.text('决策未被确认，等待可能已超时；请查看任务进度'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('提交决策'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('提交中退出再进入会应用晚到的成功结果', (tester) async {
    final pending = Completer<Object?>();
    final controller = WorkbenchController(
      projectClient: AgentProjectClient(
        DeliveryApi((_, __, ___) => pending.future),
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
    final container = ProviderContainer(
      overrides: [workbenchControllerProvider.overrideWith((_) => controller)],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentDecisionPage()),
      ),
    );
    await tester.tap(find.text('提交决策'));
    await tester.pump();
    expect(find.text('提交中…'), findsOneWidget);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: SizedBox.shrink()),
      ),
    );
    await tester.pump();
    pending.complete({'status': 'submitted'});
    await tester.pump();
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentDecisionPage()),
      ),
    );
    await tester.pump();
    expect(find.text('当前没有待提交的决策，请返回工作台查看进度。'), findsOneWidget);
    expect(find.text('提交决策'), findsNothing);
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
        overrides: [
          agentProjectClientProvider.overrideWithValue(client),
          githubClientProvider.overrideWithValue(
            GithubClient(
              DeliveryApi(
                (_, __, ___) async => {
                  'username': '',
                  'use_github': false,
                  'persisted': false,
                  'has_token': false,
                  'credential_state': 'missing',
                  'verified': false,
                },
              ),
            ),
          ),
        ],
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

  testWidgets('切账号后文件预览不会保留上一账号内容', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    var reads = 0;
    final client = AgentProjectClient(
      DeliveryApi((path, _, __) async {
        if (Uri.parse(path).path.endsWith('/files')) {
          return {
            'files': [
              {'path': 'src/main.dart'},
            ],
          };
        }
        reads++;
        return {'content': '内容$reads'};
      }),
    );
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        agentProjectClientProvider.overrideWithValue(client),
        githubClientProvider.overrideWithValue(
          GithubClient(
            DeliveryApi(
              (_, __, ___) async => {
                'username': '',
                'use_github': false,
                'persisted': false,
                'has_token': false,
                'credential_state': 'missing',
                'verified': false,
              },
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('src'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('main.dart'));
    await tester.pumpAndSettle();
    expect(find.text('内容1'), findsOneWidget);

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    expect(find.text('内容1'), findsNothing);
    expect(find.text('内容2'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('file page pushes project to github without config', (
    tester,
  ) async {
    Map? saved;
    final filesClient = AgentProjectClient(
      DeliveryApi(
        (path, _, __) async => Uri.parse(path).path.endsWith('/files')
            ? {
                'files': [
                  {'path': 'README.md'},
                ],
              }
            : {'content': '# demo'},
      ),
    );
    final github = GithubClient(
      DeliveryApi((path, method, body) async {
        if (path == '/api/v1/github/config') {
          return {
            'username': 'alice',
            'use_github': true,
            'persisted': true,
            'has_token': true,
            'credential_state': 'stored',
            'verified': false,
          };
        }
        expect(path, '/api/v1/github/save');
        expect(method, 'POST');
        saved = body as Map?;
        return {
          'success': true,
          'repo_url': 'https://github.com/alice/project',
          'commit_id': 'abc',
        };
      }),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(filesClient),
          githubClientProvider.overrideWithValue(github),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('githubSaveProject')));
    await tester.pumpAndSettle();
    expect(saved, isNotNull);
    expect(saved!.containsKey('github_config'), false);
    expect(saved!['project_name'], 'project');
    expect(saved!['project_data'], '{"README.md":"# demo"}');
    expect(find.text('https://github.com/alice/project'), findsOneWidget);
  });

  GithubClient missingGithub() => GithubClient(
    DeliveryApi(
      (_, __, ___) async => {
        'username': '',
        'use_github': false,
        'persisted': false,
        'has_token': false,
        'credential_state': 'missing',
        'verified': false,
      },
    ),
  );

  testWidgets('文件列表网络断开显示笼统错误', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(
            AgentProjectClient(
              DeliveryApi(
                (_, __, ___) async =>
                    throw const SocketException('connection lost'),
              ),
            ),
          ),
          githubClientProvider.overrideWithValue(missingGithub()),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('文件列表加载失败，请重试'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('加载中退出再进入会重新拉列表', (tester) async {
    var calls = 0;
    final pending = Completer<Object?>();
    final client = AgentProjectClient(
      DeliveryApi((path, _, __) async {
        if (!Uri.parse(path).path.endsWith('/files')) {
          return {'content': 'void main() {}'};
        }
        calls += 1;
        if (calls == 1) return pending.future;
        return {
          'files': [
            {'path': 'src/main.dart'},
          ],
        };
      }),
    );
    final github = missingGithub();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(client),
          githubClientProvider.overrideWithValue(github),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    pending.complete({
      'files': [
        {'path': 'old.dart'},
      ],
    });
    await tester.pump();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(client),
          githubClientProvider.overrideWithValue(github),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('old.dart'), findsNothing);
    await tester.tap(find.text('src'));
    await tester.pumpAndSettle();
    expect(find.text('main.dart'), findsOneWidget);
  });

  testWidgets('文件预览网络断开显示重试', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(
            AgentProjectClient(
              DeliveryApi((path, _, __) async {
                if (Uri.parse(path).path.endsWith('/files')) {
                  return {
                    'files': [
                      {'path': 'README.md'},
                    ],
                  };
                }
                throw const SocketException('connection lost');
              }),
            ),
          ),
          githubClientProvider.overrideWithValue(missingGithub()),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('README.md'));
    await tester.pump();
    await tester.pump();
    expect(find.text('文件读取失败，点击重试'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  Map<String, Object> enabledGithubConfig() => {
    'username': 'alice',
    'use_github': true,
    'persisted': true,
    'has_token': true,
    'credential_state': 'stored',
    'verified': false,
  };

  AgentProjectClient readmeFilesClient() => AgentProjectClient(
    DeliveryApi(
      (path, _, __) async => Uri.parse(path).path.endsWith('/files')
          ? {
              'files': [
                {'path': 'README.md'},
              ],
            }
          : {'content': '# demo'},
    ),
  );

  testWidgets('推送到GitHub网络断开显示笼统错误', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(readmeFilesClient()),
          githubClientProvider.overrideWithValue(
            GithubClient(
              DeliveryApi((path, method, body) async {
                if (path == '/api/v1/github/config') {
                  return enabledGithubConfig();
                }
                throw const SocketException('connection lost');
              }),
            ),
          ),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byKey(const Key('githubSaveProject')));
    await tester.pump();
    await tester.pump();
    expect(find.text('GitHub 推送失败，请先在设置中保存并启用凭据'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.textContaining('https://github.com'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('推送中再次点击不会发请求', (tester) async {
    var saves = 0;
    final pending = Completer<Object?>();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(readmeFilesClient()),
          githubClientProvider.overrideWithValue(
            GithubClient(
              DeliveryApi((path, method, body) async {
                if (path == '/api/v1/github/config') {
                  return enabledGithubConfig();
                }
                if (path == '/api/v1/github/save') {
                  saves += 1;
                  return pending.future;
                }
                throw StateError('unexpected $method $path');
              }),
            ),
          ),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byKey(const Key('githubSaveProject')));
    await tester.pump();
    expect(saves, 1);
    expect(find.text('正在推送到 GitHub'), findsOneWidget);
    await tester.tap(find.byKey(const Key('githubSaveProject')));
    await tester.pump();
    expect(saves, 1);
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
  });

  testWidgets('推送中退出再进入会丢掉结果', (tester) async {
    var saves = 0;
    final pending = Completer<Object?>();
    final filesClient = readmeFilesClient();
    final github = GithubClient(
      DeliveryApi((path, method, body) async {
        if (path == '/api/v1/github/config') {
          return enabledGithubConfig();
        }
        if (path == '/api/v1/github/save') {
          saves += 1;
          return pending.future;
        }
        throw StateError('unexpected $method $path');
      }),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(filesClient),
          githubClientProvider.overrideWithValue(github),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byKey(const Key('githubSaveProject')));
    await tester.pump();
    expect(find.text('正在推送到 GitHub'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(filesClient),
          githubClientProvider.overrideWithValue(github),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('推送到 GitHub'), findsOneWidget);
    expect(find.text('GitHub 推送失败，请先在设置中保存并启用凭据'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(saves, 1);
  });

  testWidgets('下载网络断开显示笼统错误', (tester) async {
    late Directory directory;
    await tester.runAsync(() async {
      directory = await Directory.systemTemp.createTemp('files-download-');
    });
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(
            AgentProjectClient(
              DeliveryApi(
                (path, _, __) async => Uri.parse(path).path.endsWith('/files')
                    ? {
                        'files': [
                          {'path': 'README.md'},
                        ],
                      }
                    : {'content': '# demo'},
                sendHandle: (_) async =>
                    throw const SocketException('connection lost'),
              ),
              directory: () async => directory,
            ),
          ),
          githubClientProvider.overrideWithValue(missingGithub()),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('下载 ZIP 到应用文档'));
    await tester.pump();
    await tester.pump();
    expect(find.text('下载未完成，请重试；单个项目包上限 200 MB'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.textContaining('已保存'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('再次下载失败不会残留上次的保存路径', (tester) async {
    var calls = 0;
    final client = _ScriptedDownloadClient(() {
      calls += 1;
      if (calls == 1) return Future.value('/tmp/project-first.zip');
      return Future.error(const SocketException('connection lost'));
    });
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(client),
          githubClientProvider.overrideWithValue(missingGithub()),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('下载 ZIP 到应用文档'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('已保存'), findsOneWidget);
    await tester.tap(find.text('下载 ZIP 到应用文档'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('已保存'), findsNothing);
    expect(find.text('下载未完成，请重试；单个项目包上限 200 MB'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('下载中再次点击不会发请求', (tester) async {
    var sends = 0;
    final pending = Completer<http.StreamedResponse>();
    late Directory directory;
    await tester.runAsync(() async {
      directory = await Directory.systemTemp.createTemp('files-download-');
    });
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(
            AgentProjectClient(
              DeliveryApi(
                (path, _, __) async => Uri.parse(path).path.endsWith('/files')
                    ? {
                        'files': [
                          {'path': 'README.md'},
                        ],
                      }
                    : {'content': '# demo'},
                sendHandle: (_) {
                  sends += 1;
                  return pending.future;
                },
              ),
              directory: () async => directory,
            ),
          ),
          githubClientProvider.overrideWithValue(missingGithub()),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('下载 ZIP 到应用文档'));
    await tester.pump();
    expect(sends, 1);
    expect(find.textContaining('已下载'), findsOneWidget);
    await tester.tap(find.textContaining('已下载'));
    await tester.pump();
    expect(sends, 1);
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
  });

  testWidgets('下载中退出再进入会丢掉错误', (tester) async {
    var sends = 0;
    final pending = Completer<http.StreamedResponse>();
    late Directory directory;
    await tester.runAsync(() async {
      directory = await Directory.systemTemp.createTemp('files-download-');
    });
    final client = AgentProjectClient(
      DeliveryApi(
        (path, _, __) async => Uri.parse(path).path.endsWith('/files')
            ? {
                'files': [
                  {'path': 'README.md'},
                ],
              }
            : {'content': '# demo'},
        sendHandle: (_) {
          sends += 1;
          return pending.future;
        },
      ),
      directory: () async => directory,
    );
    final github = missingGithub();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(client),
          githubClientProvider.overrideWithValue(github),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('下载 ZIP 到应用文档'));
    await tester.pump();
    expect(find.textContaining('已下载'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(client),
          githubClientProvider.overrideWithValue(github),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('下载 ZIP 到应用文档'), findsOneWidget);
    expect(find.text('下载未完成，请重试；单个项目包上限 200 MB'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(sends, 1);
  });

  testWidgets('GitHub配置加载网络断开显示未加载前往设置', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(readmeFilesClient()),
          githubClientProvider.overrideWithValue(
            GithubClient(
              DeliveryApi(
                (_, __, ___) async =>
                    throw const SocketException('connection lost'),
              ),
            ),
          ),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('GitHub 配置未加载，前往设置'), findsOneWidget);
    expect(find.byKey(const Key('githubSaveProject')), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('未启用GitHub保存显示前往设置', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(readmeFilesClient()),
          githubClientProvider.overrideWithValue(missingGithub()),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('未启用 GitHub 保存，前往设置'), findsOneWidget);
    expect(find.byKey(const Key('githubSaveProject')), findsNothing);
  });

  testWidgets('GitHub配置加载中退出再进入会重新拉取', (tester) async {
    var configs = 0;
    final pending = Completer<Object?>();
    final filesClient = readmeFilesClient();
    final github = GithubClient(
      DeliveryApi((path, method, body) async {
        if (path == '/api/v1/github/config') {
          configs += 1;
          if (configs == 1) return pending.future;
          return {
            'username': '',
            'use_github': false,
            'persisted': false,
            'has_token': false,
            'credential_state': 'missing',
            'verified': false,
          };
        }
        throw StateError('unexpected $method $path');
      }),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(filesClient),
          githubClientProvider.overrideWithValue(github),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    expect(find.text('GitHub 配置未加载，前往设置'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    pending.complete(enabledGithubConfig());
    await tester.pump();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(filesClient),
          githubClientProvider.overrideWithValue(github),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('未启用 GitHub 保存，前往设置'), findsOneWidget);
    expect(find.byKey(const Key('githubSaveProject')), findsNothing);
    expect(find.textContaining('alice'), findsNothing);
    expect(configs, 2);
  });

  testWidgets('前往设置进行中无法再次叠开设置页', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          agentProjectClientProvider.overrideWithValue(readmeFilesClient()),
          githubClientProvider.overrideWithValue(missingGithub()),
        ],
        child: const MaterialApp(home: ProjectFilesPage(project: '42/project')),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('未启用 GitHub 保存，前往设置'), findsOneWidget);
    final state = tester.state(find.byType(ProjectFilesPage)) as dynamic;
    unawaited(state.openGithubSettings());
    unawaited(state.openGithubSettings());
    await tester.pumpAndSettle();
    expect(find.text('GitHub 设置'), findsOneWidget);
    expect(
      find.byType(GithubSettingsPage, skipOffstage: false),
      findsOneWidget,
    );

    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.byType(ProjectFilesPage), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
