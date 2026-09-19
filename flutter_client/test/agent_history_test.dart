import 'dart:convert';
import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:codingmatrix_desktop/application/agent_session_providers.dart';
import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/domain/models/auth_session.dart';
import 'package:codingmatrix_desktop/infrastructure/agent/agent_session_client.dart';
import 'package:codingmatrix_desktop/infrastructure/agent/agent_stream_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/cloud_auth_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/credential_store.dart';
import 'package:codingmatrix_desktop/presentation/agent_history_page.dart';
import 'agent_delivery_test.dart' show DeliveryApi;
import 'auth_session_test.dart' show Fixture;
import 'module_lifecycle_test.dart' show ModuleAuth;

void main() {
  final payload = {
    'session_id': 's1',
    'requirement': '历史项目',
    'status': 'completed',
    'output_dir': '42/project',
    'files_generated': 2,
    'files_total': 2,
    'reconnectable': false,
  };
  AuthController signedIn({bool withSession = true}) {
    final store = CredentialStore();
    return AuthController(
      CloudAuthClient(
        baseUrl: 'https://example.com',
        httpClient: MockClient((_) async => http.Response('', 500)),
        credentialStore: store,
      ),
      store,
      session: withSession
          ? const AuthSession(
              username: 'alice',
              permissionLevel: 'normal',
              accessTokenRef: 'ref',
            )
          : null,
    );
  }

  Map<String, Object> livePayload() => {...payload, 'reconnectable': true};
  test(
    'account change ignores late history from the previous account',
    () async {
      final fixture = Fixture();
      final oldResponse = Completer<http.Response>();
      fixture.business = (_) => oldResponse.future;
      final container = ProviderContainer(
        overrides: [
          credentialStoreProvider.overrideWithValue(fixture.store),
          httpClientProvider.overrideWithValue(fixture.transport),
          cloudAuthClientProvider.overrideWithValue(fixture.auth),
        ],
      );
      addTearDown(container.dispose);
      final auth = container.read(authControllerProvider.notifier);
      await Future<void>.delayed(Duration.zero);
      await auth.login(email: 'alice@example.com', password: 'test-password');
      final subscription = container.listen(agentSessionsProvider, (_, _) {});
      addTearDown(subscription.close);
      await Future<void>.delayed(Duration.zero);
      await auth.logout();
      expect(await container.read(agentSessionsProvider.future), isEmpty);
      fixture.subject = '2';
      fixture.business = (_) async => http.Response('{"sessions":[]}', 200);
      await auth.login(
        email: 'bob@example.com',
        password: 'test-password',
        serviceUrl: 'https://two.example',
      );
      expect(await container.read(agentSessionsProvider.future), isEmpty);
      oldResponse.complete(
        http.Response.bytes(
          utf8.encode(
            jsonEncode({
              'sessions': [payload],
            }),
          ),
          200,
        ),
      );
      await Future<void>.delayed(Duration.zero);
      expect(container.read(agentSessionsProvider).value, isEmpty);
    },
  );
  test('history and detail use authenticated session endpoints', () async {
    final client = AgentSessionClient(
      DeliveryApi((path, method, body) async {
        expect(method, 'GET');
        if (path.endsWith('/sessions')) {
          return {
            'sessions': [payload],
          };
        }
        expect(path, '/api/v1/agent/sessions/s1');
        return payload;
      }),
    );
    expect((await client.list()).single.id, 's1');
    final detail = await client.detail('s1');
    expect(detail.projectPath, '42/project');
    expect(detail.reconnectable, false);
  });

  test(
    'explicit reconnect sends selected session once and never falls back',
    () async {
      final store = CredentialStore();
      final token = store.storeAccessToken('access');
      var calls = 0;
      final client = AgentStreamClient(
        baseUrl: 'https://example.com',
        credentialStore: store,
        httpClient: MockClient((request) async {
          calls++;
          final body = jsonDecode(request.body) as Map;
          expect(body['is_resume'], true);
          expect(body['session_id'], 'chosen-session');
          return http.Response('{}', 409);
        }),
      );
      await expectLater(
        client
            .generate(
              accessTokenRef: token,
              requirement: 'reconnect',
              sessionId: 'chosen-session',
              isResume: true,
            )
            .toList(),
        throwsA(isA<AgentStreamException>()),
      );
      expect(calls, 1);
    },
  );

  testWidgets(
    'history opens finished detail with files and disabled reconnect',
    (tester) async {
      final session = AgentSession.fromJson(payload);
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            agentSessionsProvider.overrideWith((_) async => [session]),
            agentSessionDetailProvider('s1').overrideWith((_) async => session),
          ],
          child: const MaterialApp(home: AgentHistoryPage()),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('历史项目'));
      await tester.pumpAndSettle();
      expect(find.text('查看项目文件'), findsOneWidget);
      final button = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, '恢复 SSE 连接'),
      );
      expect(button.onPressed, isNull);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('加载中网络断开显示重试且不泄露错误', (tester) async {
    final container = ProviderContainer(
      overrides: [
        agentSessionsProvider.overrideWith(
          (_) async => throw const SocketException('connection lost'),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentHistoryPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('加载失败，点击重试'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('历史项目'), findsNothing);
  });

  testWidgets('加载后显示会话标题', (tester) async {
    final container = ProviderContainer(
      overrides: [
        agentSessionsProvider.overrideWith(
          (_) async => [AgentSession.fromJson(payload)],
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentHistoryPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('历史项目'), findsOneWidget);
    expect(find.textContaining('completed'), findsOneWidget);
  });

  testWidgets('加载中退出再进入会重新拉取列表', (tester) async {
    var calls = 0;
    final pending = Completer<List<AgentSession>>();
    final container = ProviderContainer(
      overrides: [
        agentSessionsProvider.overrideWith((_) async {
          calls++;
          if (calls == 1) return pending.future;
          return [AgentSession.fromJson(payload)];
        }),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentHistoryPage()),
      ),
    );
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开会话历史'))),
      ),
    );
    await tester.pump();
    pending.complete([
      AgentSession.fromJson({
        ...payload,
        'session_id': 'old',
        'requirement': '旧会话',
      }),
    ]);
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentHistoryPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('历史项目'), findsOneWidget);
    expect(find.text('旧会话'), findsNothing);
    expect(calls, 2);
  });

  testWidgets('详情加载网络断开显示重试且不泄露错误', (tester) async {
    final container = ProviderContainer(
      overrides: [
        agentSessionDetailProvider('s1').overrideWith(
          (_) async => throw const SocketException('connection lost'),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('状态查询失败，点击重试'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('历史项目'), findsNothing);
  });

  testWidgets('详情加载中退出再进入会重新拉取', (tester) async {
    var calls = 0;
    final pending = Completer<AgentSession>();
    final container = ProviderContainer(
      overrides: [
        agentSessionDetailProvider('s1').overrideWith((_) async {
          calls++;
          if (calls == 1) return pending.future;
          return AgentSession.fromJson(payload);
        }),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开会话详情'))),
      ),
    );
    await tester.pump();
    pending.complete(AgentSession.fromJson({...payload, 'requirement': '旧详情'}));
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('历史项目'), findsOneWidget);
    expect(find.text('旧详情'), findsNothing);
    expect(calls, 2);
  });

  testWidgets('统计进行中无法再次触发并发请求', (tester) async {
    var calls = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        agentSessionsProvider.overrideWith((_) async => []),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((_, __, ___) async {
            calls++;
            return pending.future;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentHistoryPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byTooltip('Agent 统计'));
    await tester.pump();
    expect(calls, 4);
    await tester.tap(find.byTooltip('Agent 统计'));
    await tester.pump();
    expect(calls, 4);
    pending.complete(const <String, Object?>{'ok': true});
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('切账号关闭已打开的统计弹层', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        agentSessionsProvider.overrideWith((_) async => []),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi(
            (_, __, ___) async => const <String, Object?>{'tokens': '上一账号的统计'},
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentHistoryPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byTooltip('Agent 统计'));
    await tester.pump();
    await tester.pump();
    expect(find.text('Agent 统计'), findsOneWidget);
    expect(find.textContaining('上一账号的统计'), findsOneWidget);

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    expect(find.text('Agent 统计'), findsNothing);
    expect(find.textContaining('上一账号的统计'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('切账号后旧账号的统计弹层不会弹出', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        agentSessionsProvider.overrideWith((_) async => []),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((_, __, ___) async => pending.future),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentHistoryPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byTooltip('Agent 统计'));
    await tester.pump();

    auth.switchAccount('bob');
    await tester.pump();
    await tester.pump();

    pending.complete(const <String, Object?>{'tokens': '上一账号的统计'});
    await tester.pumpAndSettle();

    expect(find.text('Agent 统计'), findsNothing);
    expect(find.textContaining('上一账号的统计'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('统计读取网络断开会带上异常原文', (tester) async {
    final container = ProviderContainer(
      overrides: [
        agentSessionsProvider.overrideWith((_) async => []),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi(
            (_, __, ___) async =>
                throw const SocketException('connection lost'),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentHistoryPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byTooltip('Agent 统计'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('统计读取失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
  });

  testWidgets('清理缓存网络断开会带上异常原文', (tester) async {
    final container = ProviderContainer(
      overrides: [
        agentSessionsProvider.overrideWith((_) async => []),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi(
            (_, __, ___) async =>
                throw const SocketException('connection lost'),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentHistoryPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byTooltip('清理缓存'));
    await tester.pump();
    await tester.tap(find.text('清理'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('缓存清理失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
  });

  testWidgets('切账号后旧账号的缓存清理完成提示不会出现', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        agentSessionsProvider.overrideWith((_) async => []),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path == '/api/v1/agent/cache/clear') return pending.future;
            throw StateError('unexpected $method $path');
          }),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentHistoryPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byTooltip('清理缓存'));
    await tester.pump();
    await tester.tap(find.text('清理'));
    await tester.pump();
    await tester.pump();

    auth.switchAccount('bob');
    await tester.pump();
    await tester.pump();

    pending.complete(const <String, Object?>{});
    await tester.pumpAndSettle();

    expect(find.text('缓存清理请求已提交'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('查看快照进行中无法再次触发并发请求', (tester) async {
    var calls = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        agentSessionDetailProvider(
          's1',
        ).overrideWith((_) async => AgentSession.fromJson(payload)),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            if (path.contains('/snapshots/')) {
              calls++;
              return pending.future;
            }
            throw StateError('unexpected $method $path');
          }),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('查看快照'));
    await tester.pump();
    expect(calls, 1);
    await tester.tap(find.text('查看快照'), warnIfMissed: false);
    await tester.pump();
    expect(calls, 1);
    pending.complete({
      'snapshots': [
        {'tag': 't1', 'id': 't1'},
      ],
    });
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('切账号后旧账号的快照弹层不会弹出', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        agentSessionDetailProvider(
          's1',
        ).overrideWith((_) async => AgentSession.fromJson(payload)),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, _, __) async {
            if (path.contains('/snapshots/')) return pending.future;
            throw StateError('unexpected $path');
          }),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('查看快照'));
    await tester.pump();

    auth.switchAccount('bob');
    await tester.pump();
    await tester.pump();

    pending.complete({
      'snapshots': [
        {'tag': '上一账号的快照', 'id': 't1'},
      ],
    });
    await tester.pumpAndSettle();

    expect(find.text('上一账号的快照'), findsNothing);
    expect(find.byTooltip('回滚'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('快照读取网络断开会带上异常原文', (tester) async {
    final container = ProviderContainer(
      overrides: [
        agentSessionDetailProvider(
          's1',
        ).overrideWith((_) async => AgentSession.fromJson(payload)),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi(
            (_, __, ___) async =>
                throw const SocketException('connection lost'),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('查看快照'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('快照读取失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
  });

  testWidgets('并发限制网络断开会带上异常原文', (tester) async {
    final container = ProviderContainer(
      overrides: [
        agentSessionsProvider.overrideWith((_) async => []),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi(
            (_, __, ___) async =>
                throw const SocketException('connection lost'),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentHistoryPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byTooltip('并发限制'));
    await tester.pump();
    await tester.tap(find.text('保存'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('更新失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
  });

  testWidgets('快照回滚网络断开会带上异常原文', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        agentSessionDetailProvider(
          's1',
        ).overrideWith((_) async => AgentSession.fromJson(payload)),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            if (path.contains('/snapshots/')) {
              return {
                'snapshots': [
                  {'tag': 't1', 'message': 'first', 'id': 't1'},
                ],
              };
            }
            throw const SocketException('connection lost');
          }),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('查看快照'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.ensureVisible(find.byTooltip('回滚'));
    await tester.tap(find.byTooltip('回滚'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('确认'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('回滚失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
  });

  testWidgets('回滚失败后再次成功打开快照会清除旧错误', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        agentSessionDetailProvider(
          's1',
        ).overrideWith((_) async => AgentSession.fromJson(payload)),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            if (path.contains('/rollback/')) {
              throw const SocketException('connection lost');
            }
            return {
              'snapshots': [
                {'tag': 't1', 'message': 'first', 'id': 't1'},
              ],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('查看快照'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.ensureVisible(find.byTooltip('回滚'));
    await tester.tap(find.byTooltip('回滚'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('确认'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('回滚失败'), findsOneWidget);
    await tester.tap(find.text('查看快照'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.textContaining('回滚失败'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('快照差异网络断开会带上异常原文', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        agentSessionDetailProvider(
          's1',
        ).overrideWith((_) async => AgentSession.fromJson(payload)),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            if (path.contains('/snapshots/')) {
              return {
                'snapshots': [
                  {'tag': 't1', 'id': 't1'},
                  {'tag': 't2', 'id': 't2'},
                ],
              };
            }
            throw const SocketException('connection lost');
          }),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('查看快照'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.ensureVisible(find.text('比较最新两个快照'));
    await tester.tap(find.text('比较最新两个快照'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('差异读取失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
  });

  testWidgets('未登录时恢复不会发请求', (tester) async {
    var details = 0;
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith(
          (_) => signedIn(withSession: false),
        ),
        agentSessionDetailProvider(
          's1',
        ).overrideWith((_) async => AgentSession.fromJson(livePayload())),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            details += 1;
            throw StateError('unexpected $method $path');
          }),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('恢复 SSE 连接'));
    await tester.pump();
    await tester.pump();
    expect(find.text('断开并重连'), findsNothing);
    expect(find.text('恢复未成功，请刷新详情后重试'), findsNothing);
    expect(details, 0);
  });

  testWidgets('恢复SSE网络断开显示恢复未成功且不泄露错误', (tester) async {
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => signedIn()),
        agentSessionDetailProvider(
          's1',
        ).overrideWith((_) async => AgentSession.fromJson(livePayload())),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi(
            (_, __, ___) async =>
                throw const SocketException('connection lost'),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('恢复 SSE 连接'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('断开并重连'));
    await tester.pump();
    await tester.pump();
    expect(find.text('恢复未成功，请刷新详情后重试'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('恢复时服务端拒绝显示恢复未成功而不是假装成功', (tester) async {
    final store = CredentialStore();
    final tokenRef = store.storeAccessToken('access');
    var streamCalls = 0;
    final container = ProviderContainer(
      overrides: [
        credentialStoreProvider.overrideWithValue(store),
        authControllerProvider.overrideWith(
          (_) => AuthController(
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
          ),
        ),
        agentSessionClientProvider.overrideWithValue(
          AgentSessionClient(DeliveryApi((_, __, ___) async => livePayload())),
        ),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi(
            (_, __, ___) async => livePayload(),
            sendHandle: (_) async {
              streamCalls++;
              return http.StreamedResponse(
                const Stream<List<int>>.empty(),
                409,
              );
            },
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('恢复 SSE 连接'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('断开并重连'));
    await tester.pump();
    await tester.pump();
    expect(streamCalls, 1);
    expect(find.text('恢复未成功，请刷新详情后重试'), findsOneWidget);
    expect(find.textContaining('HTTP 409'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('恢复中退出再进入会丢掉错误', (tester) async {
    var details = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => signedIn()),
        agentSessionDetailProvider(
          's1',
        ).overrideWith((_) async => AgentSession.fromJson(livePayload())),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            details += 1;
            return pending.future;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('恢复 SSE 连接'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('断开并重连'));
    await tester.pump();
    expect(find.text('正在确认'), findsOneWidget);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开会话详情'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('恢复 SSE 连接'), findsOneWidget);
    expect(find.text('恢复未成功，请刷新详情后重试'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(details, 1);
  });

  testWidgets('快照读取中退出再进入会丢掉错误', (tester) async {
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        agentSessionDetailProvider(
          's1',
        ).overrideWith((_) async => AgentSession.fromJson(payload)),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            if (path.contains('/snapshots/')) return pending.future;
            throw StateError('unexpected $method $path');
          }),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('查看快照'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开会话详情'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('快照读取失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('查看快照'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('快照差异读取中退出再进入会丢掉错误', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        agentSessionDetailProvider(
          's1',
        ).overrideWith((_) async => AgentSession.fromJson(payload)),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            if (path.contains('/snapshots/')) {
              return {
                'snapshots': [
                  {'tag': 't1', 'id': 't1'},
                  {'tag': 't2', 'id': 't2'},
                ],
              };
            }
            if (path.contains('/snapshot/diff')) return pending.future;
            throw StateError('unexpected $method $path');
          }),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('查看快照'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.ensureVisible(find.text('比较最新两个快照'));
    await tester.tap(find.text('比较最新两个快照'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开会话详情'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentSessionDetailPage(id: 's1')),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('差异读取失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('查看快照'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
