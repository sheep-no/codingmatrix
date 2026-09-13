import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/infrastructure/model/model_client.dart';
import 'package:codingmatrix_desktop/presentation/model_list_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'agent_delivery_test.dart' show DeliveryApi;

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
          DeliveryApi((_, __, ___) async => {
            'models': [modelItem],
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
    expect(find.textContaining('通用对话'), findsOneWidget);
    expect(find.text('默认'), findsOneWidget);
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
        {
          'id': 'old',
          'name': '旧模型',
          'model_key': 'old',
          'description': '应丢弃',
        },
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
}
