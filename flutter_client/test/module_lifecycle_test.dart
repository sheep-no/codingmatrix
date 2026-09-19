import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/application/image_generation_controller.dart';
import 'package:codingmatrix_desktop/application/workflow_controller.dart';
import 'package:codingmatrix_desktop/application/github_controller.dart';
import 'package:codingmatrix_desktop/application/workbench_controller.dart';
import 'package:codingmatrix_desktop/domain/models/auth_session.dart';
import 'package:codingmatrix_desktop/domain/models/unified_models.dart';
import 'package:codingmatrix_desktop/domain/models/image_generation.dart';
import 'package:codingmatrix_desktop/domain/models/agent_decision.dart';
import 'package:codingmatrix_desktop/presentation/agent_decision_page.dart';
import 'package:codingmatrix_desktop/presentation/github_settings_page.dart';
import 'package:codingmatrix_desktop/presentation/project_files_page.dart';
import 'package:codingmatrix_desktop/presentation/workbench_page.dart';
import 'package:codingmatrix_desktop/presentation/ppt_page.dart';
import 'package:codingmatrix_desktop/infrastructure/agent/agent_project_client.dart';
import 'package:codingmatrix_desktop/infrastructure/github/github_client.dart';
import 'agent_delivery_test.dart' show DeliveryApi;
import 'auth_session_test.dart' show Fixture;
import 'image_generation_test.dart' show key, pixel;

class ModuleAuth extends AuthController {
  ModuleAuth(Fixture fixture) : super(fixture.auth, fixture.store);
  void switchAccount(String id) {
    state = AuthState(
      session: AuthSession(
        username: id,
        permissionLevel: 'normal',
        accessTokenRef: id,
      ),
    );
  }
}

void main() {
  testWidgets('320px workbench opens modules from the navigation drawer', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authControllerProvider.overrideWith(
            (_) => ModuleAuth(Fixture())..switchAccount('alice'),
          ),
          authenticatedClientProvider.overrideWithValue(
            DeliveryApi((_, __, ___) async => {}),
          ),
        ],
        child: const MaterialApp(home: WorkbenchPage()),
      ),
    );
    await tester.pumpAndSettle();
    const modules = <String, String>{
      'image': '图片生成',
      'workflow': '工作流执行',
      'github': 'GitHub 设置',
    };
    for (final entry in modules.entries) {
      await tester.tap(find.byIcon(Icons.menu));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.byKey(Key('capabilityNav_${entry.key}')));
      await tester.tap(find.byKey(Key('capabilityNav_${entry.key}')));
      await tester.pumpAndSettle();
      expect(find.widgetWithText(AppBar, entry.value), findsOneWidget);
      expect(tester.takeException(), isNull);
    }
  });
  test(
    'account change recreates all module states and ignores pending image result',
    () async {
      final auth = ModuleAuth(Fixture())..switchAccount('alice');
      final pending = Completer<Object?>();
      final container = ProviderContainer(
        overrides: [
          authControllerProvider.overrideWith((_) => auth),
          authenticatedClientProvider.overrideWithValue(
            DeliveryApi((_, __, ___) => pending.future),
          ),
        ],
      );
      addTearDown(container.dispose);
      final image = container.listen(
        imageGenerationControllerProvider,
        (_, __) {},
      );
      final workflow = container.listen(workflowControllerProvider, (_, __) {});
      final github = container.listen(githubControllerProvider, (_, __) {});
      final oldImage = container.read(
        imageGenerationControllerProvider.notifier,
      );
      final oldWorkflow = container.read(workflowControllerProvider.notifier);
      final oldGithub = container.read(githubControllerProvider.notifier);
      final run = oldImage.generate(
        const ImageGenerationInput(prompt: 'private'),
        key,
      );
      auth.switchAccount('bob');
      expect(image.read().images, isEmpty);
      expect(image.read().busy, false);
      expect(workflow.read().snapshot.id, isNull);
      expect(github.read().binding, isNull);
      expect(
        identical(
          oldWorkflow,
          container.read(workflowControllerProvider.notifier),
        ),
        false,
      );
      expect(
        identical(oldGithub, container.read(githubControllerProvider.notifier)),
        false,
      );
      pending.complete({
        'success': true,
        'images': [pixel],
      });
      await run;
      expect(image.read().images, isEmpty);
    },
  );

  testWidgets('account switch clears project files and loads the new account', (
    tester,
  ) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    var files = 0;
    final project = AgentProjectClient(
      DeliveryApi((path, _, __) async {
        if (Uri.parse(path).path.endsWith('/files')) {
          files++;
          return {
            'files': [
              {'path': files == 1 ? 'old.txt' : 'new.txt'},
            ],
          };
        }
        return {'content': ''};
      }),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authControllerProvider.overrideWith((_) => auth),
          agentProjectClientProvider.overrideWithValue(project),
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
    expect(find.text('old.txt'), findsOneWidget);

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    expect(find.text('old.txt'), findsNothing);
    expect(find.text('new.txt'), findsOneWidget);
    expect(files, 2);
    expect(tester.takeException(), isNull);
  });

  testWidgets('account switch clears PPT draft and generation state', (
    tester,
  ) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authControllerProvider.overrideWith((_) => auth),
          authenticatedClientProvider.overrideWithValue(
            DeliveryApi((path, _, __) async {
              if (path == '/api/v1/pptx/generate_task') {
                return {'task_id': 't1'};
              }
              if (path == '/api/v1/tasks/t1') {
                return {
                  'status': 'completed',
                  'result': {'ppt_id': 'p1'},
                };
              }
              return {};
            }),
          ),
        ],
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.enterText(find.byType(TextField), '主题草稿');
    await tester.tap(find.text('生成 PPT'));
    await tester.pump();
    await tester.pump();
    await tester.pump();
    expect(find.text('下载 PPTX'), findsOneWidget);

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    expect(find.text('下载 PPTX'), findsNothing);
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller?.text,
      isEmpty,
    );
    expect(find.textContaining('生成完成'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'account switch clears GitHub draft and discards late old configuration',
    (tester) async {
      final auth = ModuleAuth(Fixture())..switchAccount('alice');
      final pending = Completer<Object?>();
      var loads = 0;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authControllerProvider.overrideWith((_) => auth),
            authenticatedClientProvider.overrideWithValue(
              DeliveryApi((_, __, ___) {
                loads++;
                return loads == 1
                    ? pending.future
                    : Future.value({
                        'username': 'bob',
                        'persisted': true,
                        'has_token': false,
                        'credential_state': 'missing',
                        'use_github': false,
                      });
              }),
            ),
          ],
          child: const MaterialApp(home: GithubSettingsPage()),
        ),
      );
      await tester.pump();
      auth.switchAccount('bob');
      await tester.pumpAndSettle();
      pending.complete({'username': 'alice', 'persisted': true});
      await tester.pumpAndSettle();
      final username = tester.widget<TextField>(
        find.byKey(const Key('githubUsername')),
      );
      expect(username.controller!.text, 'bob');
      await tester.enterText(
        find.byKey(const Key('githubToken')),
        'draft-secret',
      );
      auth.switchAccount('carol');
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<TextField>(find.byKey(const Key('githubToken')))
            .controller!
            .text,
        isEmpty,
      );
      await tester.pumpWidget(const SizedBox());
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'account switch does not reuse the previous account decision choice',
    (tester) async {
      final auth = ModuleAuth(Fixture())..switchAccount('alice');
      final submitted = <Map<String, String>>[];
      WorkbenchController buildWorkbench() {
        final controller = WorkbenchController(
          projectClient: AgentProjectClient(
            DeliveryApi((_, __, body) async {
              submitted.add(Map<String, String>.from(body as Map));
              return {'status': 'submitted'};
            }),
          ),
        );
        controller.state = WorkbenchState(
          task: const Task(taskId: 't', sessionId: 's', status: 'running'),
          decisions: [
            AgentDecision.fromJson({
              'id': 'database_choice',
              'question': '数据库选型',
              'context': '持久化',
              'options': [
                {'label': 'SQLite', 'description': '单机'},
                {'label': 'PostgreSQL', 'description': '服务端'},
              ],
              'default': 'SQLite',
            }),
          ],
        );
        return controller;
      }

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authControllerProvider.overrideWith((_) => auth),
            workbenchControllerProvider.overrideWith((ref) {
              ref.watch(
                authControllerProvider.select((s) => s.session?.accessTokenRef),
              );
              return buildWorkbench();
            }),
          ],
          child: const MaterialApp(home: AgentDecisionPage()),
        ),
      );
      await tester.pump();

      await tester.tap(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();
      await tester.tap(find.text('PostgreSQL').last);
      await tester.pumpAndSettle();

      auth.switchAccount('bob');
      await tester.pumpAndSettle();
      expect(find.text('提交决策'), findsOneWidget);

      await tester.tap(find.text('提交决策'));
      await tester.pumpAndSettle();

      expect(submitted.single, {'database_choice': 'SQLite'});
      expect(tester.takeException(), isNull);
    },
  );
}
