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
import 'package:codingmatrix_desktop/infrastructure/agent/agent_session_client.dart';
import 'package:codingmatrix_desktop/infrastructure/agent/agent_stream_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/credential_store.dart';
import 'package:codingmatrix_desktop/presentation/agent_history_page.dart';
import 'agent_delivery_test.dart' show DeliveryApi;
import 'auth_session_test.dart' show Fixture;

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
}
