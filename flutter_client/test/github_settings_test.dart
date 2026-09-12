import 'dart:async';
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
}
