import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:codingmatrix_desktop/application/github_controller.dart';
import 'package:codingmatrix_desktop/presentation/github_settings_page.dart';
import 'package:codingmatrix_desktop/infrastructure/github/github_client.dart';
import 'package:codingmatrix_desktop/domain/models/github_binding.dart';
import 'agent_delivery_test.dart' show DeliveryApi;

void main() {
  const stored = {
    'username': 'alice',
    'use_github': true,
    'persisted': true,
    'has_token': true,
    'credential_state': 'stored',
    'verified': false,
  };
  test(
    'save retains token, disables integration and rejects business failure',
    () async {
      var calls = 0;
      final controller = GithubController(
        GithubClient(
          DeliveryApi((_, method, body) async {
            if (method == 'GET') return stored;
            calls++;
            expect(body, {
              'username': 'alice',
              'token': '',
              'use_github': false,
            });
            return {'success': false};
          }),
        ),
      );
      await controller.load();
      expect(
        await controller.save(username: 'bob', token: '', useGithub: false),
        false,
      );
      expect(calls, 0);
      expect(
        await controller.save(username: 'alice', token: '', useGithub: false),
        false,
      );
      expect(calls, 1);
      expect(controller.state.binding!.configured, true);
      expect(controller.state.error, isNotNull);
      controller.dispose();
    },
  );
  test('duplicate saves and responses after disposal are ignored', () async {
    final pending = Completer<Object?>();
    var calls = 0;
    final controller = GithubController(
      GithubClient(
        DeliveryApi((_, __, ___) {
          calls++;
          return pending.future;
        }),
      ),
    );
    final save = controller.save(
      username: 'alice',
      token: 'test-secret',
      useGithub: true,
    );
    expect(
      await controller.save(
        username: 'alice',
        token: 'test-secret',
        useGithub: true,
      ),
      false,
    );
    controller.dispose();
    pending.complete({'success': true, ...stored});
    expect(await save, false);
    expect(calls, 1);
  });
  testWidgets(
    'narrow configuration shows persisted state and accepts blank token',
    (tester) async {
      tester.view.physicalSize = const Size(320, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      var saved = false;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            githubControllerProvider.overrideWith(
              (_) => GithubController(
                GithubClient(
                  DeliveryApi((_, method, body) async {
                    if (method == 'GET') return stored;
                    expect((body as Map)['token'], '');
                    saved = true;
                    return {'success': true, ...stored};
                  }),
                ),
              ),
            ),
          ],
          child: const MaterialApp(home: GithubSettingsPage()),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('凭据状态：已加密保存'), findsOneWidget);
      expect(find.text('远端验证：尚未验证'), findsOneWidget);
      await tester.tap(find.byKey(const Key('githubSave')));
      await tester.pumpAndSettle();
      expect(saved, true);
      expect(find.text('配置已保存'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
  test(
    'GitHub config maps GET and POST contracts without retaining token in UI model',
    () async {
      final client = GithubClient(
        DeliveryApi((path, method, body) async {
          if (method == 'GET') {
            return {'username': 'alice', 'token': '', 'use_github': false};
          }
          expect(path, '/api/v1/github/config');
          expect((body as Map)['use_github'], true);
          return {
            'success': true,
            'message': '已保存',
            'username': 'alice',
            'use_github': true,
          };
        }),
      );
      final current = await client.load();
      expect(current, isA<GithubBinding>());
      expect(current.token, isEmpty);
      final saved = await client.save(
        username: 'alice',
        token: 'secret',
        useGithub: true,
      );
      expect(saved.username, 'alice');
      expect(saved.token, isEmpty);
      expect(saved.verified, false);
    },
  );
  test('verify and list contracts map repos branches and commits', () async {
    final client = GithubClient(
      DeliveryApi((path, method, body) async {
        if (path == '/api/v1/github/verify') {
          expect(method, 'POST');
          return {
            'success': true,
            'verified': true,
            'login': 'alice',
            'message': 'GitHub 凭据有效',
          };
        }
        if (path == '/api/v1/github/repos') {
          return {
            'repos': [
              {
                'full_name': 'alice/demo',
                'name': 'demo',
                'owner': 'alice',
                'private': false,
                'default_branch': 'main',
              },
            ],
          };
        }
        if (path.endsWith('/branches')) {
          return {
            'branches': [
              {'name': 'main', 'sha': 'abc1234', 'protected': false},
            ],
          };
        }
        expect(path.contains('sha=main'), true);
        return {
          'commits': [
            {
              'sha': 'abc1234def',
              'message': 'init',
              'author': 'Alice',
              'date': '2026-09-12T00:00:00Z',
            },
          ],
        };
      }),
    );
    final verified = await client.verify();
    expect(verified['verified'], true);
    expect(verified.containsKey('token'), false);
    final repos = await client.listRepos();
    expect(repos.single.fullName, 'alice/demo');
    final branches = await client.listBranches('alice', 'demo');
    expect(branches.single.name, 'main');
    final commits = await client.listCommits('alice', 'demo', sha: 'main');
    expect(commits.single.message, 'init');
  });
  test('verify copies verified onto binding without retaining token', () async {
    final controller = GithubController(
      GithubClient(
        DeliveryApi((path, method, _) async {
          if (method == 'GET') return stored;
          expect(path, '/api/v1/github/verify');
          return {
            'success': true,
            'verified': true,
            'message': 'GitHub 凭据有效',
          };
        }),
      ),
    );
    await controller.load();
    expect(controller.state.binding!.verified, false);
    expect(await controller.verify(), true);
    expect(controller.state.binding!.verified, true);
    expect(controller.state.binding!.token, isEmpty);
    controller.dispose();
  });
  test('saveProject omits github_config when using stored credentials', () async {
    final client = GithubClient(
      DeliveryApi((path, method, body) async {
        expect(path, '/api/v1/github/save');
        expect(method, 'POST');
        expect((body as Map).containsKey('github_config'), false);
        return {
          'success': true,
          'message': 'ok',
          'commit_id': 'abc',
        };
      }),
    );
    final result = await client.saveProject(
      projectName: 'demo',
      projectDescription: '',
      projectData: '{"README.md":"# demo"}',
    );
    expect(result['success'], true);
  });

  test('githubRepoNameFromProject uses last path segment', () {
    expect(githubRepoNameFromProject('42/demo-app'), 'demo-app');
    expect(githubRepoNameFromProject('42/项目'), 'project');
  });

  testWidgets('加载中网络断开显示配置加载失败', (tester) async {
    final container = ProviderContainer(
      overrides: [
        githubControllerProvider.overrideWith(
          (_) => GithubController(
            GithubClient(
              DeliveryApi(
                (_, __, ___) async =>
                    throw const SocketException('connection lost'),
              ),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('GitHub 配置加载失败，请重试'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
  });

  testWidgets('加载后显示已保存凭据', (tester) async {
    final container = ProviderContainer(
      overrides: [
        githubControllerProvider.overrideWith(
          (_) => GithubController(
            GithubClient(DeliveryApi((_, __, ___) async => stored)),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('凭据状态：已加密保存'), findsOneWidget);
    expect(
      tester
          .widget<TextField>(find.byKey(const Key('githubUsername')))
          .controller
          ?.text,
      'alice',
    );
  });

  testWidgets('加载中退出再进入会重新拉取配置', (tester) async {
    var calls = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        githubControllerProvider.overrideWith(
          (_) => GithubController(
            GithubClient(
              DeliveryApi((_, __, ___) async {
                calls++;
                if (calls == 1) return pending.future;
                return stored;
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    expect(find.byType(LinearProgressIndicator), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 GitHub'))),
      ),
    );
    await tester.pump();
    pending.complete({
      'username': 'olduser',
      'use_github': true,
      'persisted': true,
      'has_token': true,
      'credential_state': 'stored',
      'verified': false,
    });
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('凭据状态：已加密保存'), findsOneWidget);
    expect(
      tester
          .widget<TextField>(find.byKey(const Key('githubUsername')))
          .controller
          ?.text,
      'alice',
    );
    expect(find.text('olduser'), findsNothing);
    expect(calls, 2);
  });

  testWidgets('提交配置网络断开显示结果未知', (tester) async {
    final container = ProviderContainer(
      overrides: [
        githubControllerProvider.overrideWith(
          (_) => GithubController(
            GithubClient(
              DeliveryApi((path, method, body) async {
                if (method == 'GET') return stored;
                throw const SocketException('connection lost');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byKey(const Key('githubSave')));
    await tester.pump();
    await tester.pump();
    expect(find.text('GitHub 配置提交失败或结果未知，请重新读取配置确认状态'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('验证凭据网络断开显示验证失败', (tester) async {
    final container = ProviderContainer(
      overrides: [
        githubControllerProvider.overrideWith(
          (_) => GithubController(
            GithubClient(
              DeliveryApi((path, method, body) async {
                if (method == 'GET') return stored;
                throw const SocketException('connection lost');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byKey(const Key('githubVerify')));
    await tester.pump();
    await tester.pump();
    expect(find.text('GitHub 验证失败，请确认已保存凭据'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('验证中退出再进入会重新拉取配置', (tester) async {
    var verifies = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        githubControllerProvider.overrideWith(
          (_) => GithubController(
            GithubClient(
              DeliveryApi((path, method, body) async {
                if (method == 'GET') return stored;
                verifies += 1;
                if (verifies == 1) return pending.future;
                return {'verified': true, 'message': 'GitHub 凭据有效'};
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byKey(const Key('githubVerify')));
    await tester.pump();
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 GitHub'))),
      ),
    );
    await tester.pump();
    pending.complete({'verified': true, 'message': 'late-verify'});
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('凭据状态：已加密保存'), findsOneWidget);
    expect(find.text('late-verify'), findsNothing);
    expect(find.text('GitHub 凭据有效'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
  });

  testWidgets('提交中退出再进入会重新拉取配置', (tester) async {
    var posts = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        githubControllerProvider.overrideWith(
          (_) => GithubController(
            GithubClient(
              DeliveryApi((path, method, body) async {
                if (method == 'GET') return stored;
                posts += 1;
                if (posts == 1) return pending.future;
                return {'success': true, ...stored};
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byKey(const Key('githubSave')));
    await tester.pump();
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 GitHub'))),
      ),
    );
    await tester.pump();
    pending.complete({'success': true, ...stored, 'username': 'late-user'});
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('凭据状态：已加密保存'), findsOneWidget);
    expect(find.text('配置已保存'), findsNothing);
    expect(find.text('late-user'), findsNothing);
    expect(
      tester
          .widget<TextField>(find.byKey(const Key('githubUsername')))
          .controller
          ?.text,
      'alice',
    );
  });

  Map<String, Object> demoRepo() => {
    'full_name': 'alice/demo',
    'name': 'demo',
    'owner': 'alice',
    'private': false,
    'default_branch': 'main',
  };

  Map<String, Object> demoBranch() => {
    'name': 'main',
    'sha': 'abc1234',
    'protected': false,
  };

  testWidgets('读取仓库列表网络断开显示失败', (tester) async {
    final container = ProviderContainer(
      overrides: [
        githubControllerProvider.overrideWith(
          (_) => GithubController(
            GithubClient(
              DeliveryApi((path, method, body) async {
                if (path.contains('/repos')) {
                  throw const SocketException('connection lost');
                }
                if (method == 'GET') return stored;
                throw StateError('unexpected $method $path');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byKey(const Key('githubListRepos')));
    await tester.pump();
    await tester.pump();
    expect(find.text('仓库列表读取失败，请先验证凭据'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('读取分支网络断开显示失败', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        githubControllerProvider.overrideWith(
          (_) => GithubController(
            GithubClient(
              DeliveryApi((path, method, body) async {
                if (path.contains('/branches')) {
                  throw const SocketException('connection lost');
                }
                if (path.contains('/repos')) {
                  return {
                    'repos': [demoRepo()],
                  };
                }
                if (method == 'GET') return stored;
                throw StateError('unexpected $method $path');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byKey(const Key('githubListRepos')));
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.text('alice/demo'));
    await tester.tap(find.text('alice/demo'));
    await tester.pump();
    await tester.pump();
    expect(find.text('分支列表读取失败'), findsOneWidget);
    expect(find.text('alice/demo'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('读取分支中退出再进入会丢掉列表', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        githubControllerProvider.overrideWith(
          (_) => GithubController(
            GithubClient(
              DeliveryApi((path, method, body) async {
                if (path.contains('/branches')) return pending.future;
                if (path.contains('/repos')) {
                  return {
                    'repos': [demoRepo()],
                  };
                }
                if (method == 'GET') return stored;
                throw StateError('unexpected $method $path');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byKey(const Key('githubListRepos')));
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.text('alice/demo'));
    await tester.tap(find.text('alice/demo'));
    await tester.pump();
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 GitHub'))),
      ),
    );
    await tester.pump();
    pending.complete({
      'branches': [demoBranch()],
    });
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('凭据状态：已加密保存'), findsOneWidget);
    expect(find.text('alice/demo'), findsNothing);
    expect(find.text('main'), findsNothing);
  });

  testWidgets('读取仓库中退出再进入会丢掉列表', (tester) async {
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        githubControllerProvider.overrideWith(
          (_) => GithubController(
            GithubClient(
              DeliveryApi((path, method, body) async {
                if (path.contains('/repos')) return pending.future;
                if (method == 'GET') return stored;
                throw StateError('unexpected $method $path');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byKey(const Key('githubListRepos')));
    await tester.pump();
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 GitHub'))),
      ),
    );
    await tester.pump();
    pending.complete({
      'repos': [demoRepo()],
    });
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('凭据状态：已加密保存'), findsOneWidget);
    expect(find.text('alice/demo'), findsNothing);
  });

  test('未选仓库时不会读取提交', () async {
    var calls = 0;
    final controller = GithubController(
      GithubClient(
        DeliveryApi((_, __, ___) async {
          calls += 1;
          return stored;
        }),
      ),
    );
    await controller.loadCommitsForSelection('main');
    expect(calls, 0);
    controller.dispose();
  });

  testWidgets('读取提交列表网络断开显示失败', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        githubControllerProvider.overrideWith(
          (_) => GithubController(
            GithubClient(
              DeliveryApi((path, method, body) async {
                if (path.contains('/commits')) {
                  throw const SocketException('connection lost');
                }
                if (path.contains('/branches')) {
                  return {
                    'branches': [demoBranch()],
                  };
                }
                if (path.contains('/repos')) {
                  return {
                    'repos': [demoRepo()],
                  };
                }
                if (method == 'GET') return stored;
                throw StateError('unexpected $method $path');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byKey(const Key('githubListRepos')));
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.text('alice/demo'));
    await tester.tap(find.text('alice/demo'));
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.widgetWithText(ActionChip, 'main'));
    await tester.tap(find.widgetWithText(ActionChip, 'main'));
    await tester.pump();
    await tester.pump();
    expect(find.text('提交列表读取失败'), findsOneWidget);
    expect(find.text('alice/demo'), findsOneWidget);
    expect(find.widgetWithText(ActionChip, 'main'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('读取提交中退出再进入会丢掉列表', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        githubControllerProvider.overrideWith(
          (_) => GithubController(
            GithubClient(
              DeliveryApi((path, method, body) async {
                if (path.contains('/commits')) return pending.future;
                if (path.contains('/branches')) {
                  return {
                    'branches': [demoBranch()],
                  };
                }
                if (path.contains('/repos')) {
                  return {
                    'repos': [demoRepo()],
                  };
                }
                if (method == 'GET') return stored;
                throw StateError('unexpected $method $path');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byKey(const Key('githubListRepos')));
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.text('alice/demo'));
    await tester.tap(find.text('alice/demo'));
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.widgetWithText(ActionChip, 'main'));
    await tester.tap(find.widgetWithText(ActionChip, 'main'));
    await tester.pump();
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 GitHub'))),
      ),
    );
    await tester.pump();
    pending.complete({
      'commits': [
        {
          'sha': 'deadbeef',
          'message': 'late commit',
          'author': 'alice',
        },
      ],
    });
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: GithubSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('凭据状态：已加密保存'), findsOneWidget);
    expect(find.text('alice/demo'), findsNothing);
    expect(find.text('late commit'), findsNothing);
  });
}
