import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/infrastructure/model/model_client.dart';
import 'package:codingmatrix_desktop/presentation/model_list_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'agent_delivery_test.dart' show DeliveryApi;
import 'auth_session_test.dart' show Fixture;
import 'module_lifecycle_test.dart' show ModuleAuth;

const modelItem = {
  'id': 'm1',
  'name': 'GLM-4',
  'model_key': 'glm-4',
  'description': '通用对话',
  'capabilities': ['chat', 'code'],
  'is_default': true,
};

void main() {
  test('列出模型解析 models 字段', () async {
    final client = ModelClient(
      DeliveryApi((path, method, body) async {
        expect(path, '/api/v1/models/');
        expect(method, 'GET');
        return {
          'models': [modelItem],
        };
      }),
    );
    final items = await client.list();
    expect(items.single.name, 'GLM-4');
    expect(items.single.isDefault, isTrue);
    expect(items.single.capabilities, ['chat', 'code']);
  });

  test('列出模型网络断开会失败', () async {
    final client = ModelClient(
      DeliveryApi(
        (_, __, ___) async => throw const SocketException('connection lost'),
      ),
    );
    await expectLater(
      client.list(),
      throwsA(
        isA<SocketException>().having(
          (error) => error.message,
          'message',
          'connection lost',
        ),
      ),
    );
  });

  testWidgets('加载后显示默认模型', (tester) async {
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi(
            (_, __, ___) async => {
              'models': [modelItem],
            },
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ModelListPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('GLM-4'), findsOneWidget);
    expect(find.textContaining('通用对话'), findsOneWidget);
    expect(find.text('默认'), findsOneWidget);
  });

  testWidgets('切换账号清空旧模型并重新拉列表', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    var lists = 0;
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((_, __, ___) async {
            lists++;
            return lists == 1
                ? {
                    'models': [
                      {
                        'id': 'old',
                        'name': '旧模型',
                        'model_key': 'old',
                        'description': '旧',
                      },
                    ],
                  }
                : {
                    'models': [modelItem],
                  };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ModelListPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('旧模型'), findsOneWidget);

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    expect(find.text('旧模型'), findsNothing);
    expect(find.text('GLM-4'), findsOneWidget);
    expect(lists, 2);
  });

  testWidgets('切换账号时旧账号未完成的加载不会卡住新账号', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final pending = Completer<Object?>();
    var lists = 0;
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((_, __, ___) async {
            lists++;
            if (lists == 1) return pending.future;
            return {
              'models': [modelItem],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ModelListPage()),
      ),
    );
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    auth.switchAccount('bob');
    await tester.pump();
    await tester.pump();

    expect(find.text('GLM-4'), findsOneWidget);
    expect(lists, 2);

    pending.complete({
      'models': [
        {'id': 'old', 'name': '旧模型', 'model_key': 'old', 'description': '旧'},
      ],
    });
    await tester.pump();
    await tester.pump();

    expect(find.text('旧模型'), findsNothing);
    expect(find.text('GLM-4'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('加载中网络断开显示错误', (tester) async {
    final container = ProviderContainer(
      overrides: [
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
        child: const MaterialApp(home: ModelListPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('GLM-4'), findsNothing);
  });

  testWidgets('加载中退出再进入会重新拉取列表', (tester) async {
    var calls = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((_, __, ___) async {
            calls++;
            if (calls == 1) return pending.future;
            return {
              'models': [modelItem],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ModelListPage()),
      ),
    );
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开模型列表'))),
      ),
    );
    await tester.pump();
    pending.complete({
      'models': [
        {'id': 'old', 'name': '旧模型', 'model_key': 'old', 'description': '应丢弃'},
      ],
    });
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ModelListPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('GLM-4'), findsOneWidget);
    expect(find.text('旧模型'), findsNothing);
    expect(calls, 2);
  });

  testWidgets('刷新进行中无法再次触发并发请求', (tester) async {
    var calls = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((_, __, ___) async {
            calls++;
            if (calls == 1) {
              return {
                'models': [modelItem],
              };
            }
            return pending.future;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ModelListPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('GLM-4'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.refresh));
    await tester.tap(find.byIcon(Icons.refresh), warnIfMissed: false);
    await tester.pump();
    expect(calls, 2);

    pending.complete({
      'models': [modelItem],
    });
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}
