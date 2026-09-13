import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/infrastructure/provider/dynamic_provider_client.dart';
import 'package:codingmatrix_desktop/presentation/dynamic_provider_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'agent_delivery_test.dart' show DeliveryApi;

const providerItem = {
  'id': 'p1',
  'name': '自定义 GLM',
  'base_url': 'https://api.example.com/v1',
  'protocol': 'openai',
  'enabled': true,
  'models': ['glm-4'],
};

void main() {
  test('列出供应商解析数组响应', () async {
    final client = DynamicProviderClient(
      DeliveryApi((path, method, body) async {
        expect(path, '/api/v1/providers');
        expect(method, 'GET');
        return [providerItem];
      }),
    );
    final items = await client.list();
    expect(items.single.name, '自定义 GLM');
    expect(items.single.protocol, 'openai');
    expect(items.single.models, ['glm-4']);
  });

  test('列出供应商网络断开会失败', () async {
    final client = DynamicProviderClient(
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

  testWidgets('加载后显示供应商', (tester) async {
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((_, __, ___) async => [providerItem]),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: DynamicProviderPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('自定义 GLM'), findsOneWidget);
    expect(find.textContaining('https://api.example.com/v1'), findsOneWidget);
    expect(find.textContaining('openai'), findsOneWidget);
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
        child: const MaterialApp(home: DynamicProviderPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('自定义 GLM'), findsNothing);
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
            return [providerItem];
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: DynamicProviderPage()),
      ),
    );
    await tester.pump();
    expect(find.text('动态 Provider'), findsOneWidget);
    expect(find.text('自定义 GLM'), findsNothing);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开供应商'))),
      ),
    );
    await tester.pump();
    pending.complete([
      {
        'id': 'old',
        'name': '旧供应商',
        'base_url': 'https://old.example.com',
        'protocol': 'anthropic',
        'enabled': false,
        'models': const [],
      },
    ]);
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: DynamicProviderPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('自定义 GLM'), findsOneWidget);
    expect(find.text('旧供应商'), findsNothing);
    expect(calls, 2);
  });
}
