import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/infrastructure/provider/dynamic_provider_client.dart';
import 'package:codingmatrix_desktop/presentation/dynamic_provider_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'agent_delivery_test.dart' show DeliveryApi;
import 'auth_session_test.dart' show Fixture;
import 'module_lifecycle_test.dart' show ModuleAuth;

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

  testWidgets('切换账号清空供应商草稿并重新拉列表', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    var lists = 0;
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (method == 'GET' && path == '/api/v1/providers') {
              lists++;
              return [providerItem];
            }
            return null;
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
    await tester.pump();
    await tester.enterText(find.byType(TextField).at(0), '草稿名称');

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    expect(
      tester.widget<TextField>(find.byType(TextField).at(0)).controller?.text,
      isEmpty,
    );
    expect(find.text('自定义 GLM'), findsOneWidget);
    expect(lists, 2);
  });

  testWidgets('切换账号重置协议选择', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
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
    expect(find.text('OpenAI 协议'), findsOneWidget);

    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Anthropic 协议').last);
    await tester.pumpAndSettle();
    expect(find.text('Anthropic 协议'), findsOneWidget);

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    expect(find.text('OpenAI 协议'), findsOneWidget);
    expect(find.text('Anthropic 协议'), findsNothing);
  });

  testWidgets('添加网络断开显示失败原文', (tester) async {
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            if (method == 'POST' && path == '/api/v1/providers') {
              expect(body, {
                'name': 'custom',
                'base_url': 'https://llm.example.com',
                'protocol': 'openai',
                'api_key': 'sk-test',
              });
              throw const SocketException('connection lost');
            }
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
    await tester.pump();
    await tester.enterText(find.byType(TextField).at(0), 'custom');
    await tester.enterText(
      find.byType(TextField).at(1),
      'https://llm.example.com',
    );
    await tester.enterText(find.byType(TextField).at(2), 'sk-test');
    await tester.tap(find.text('添加供应商'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('自定义 GLM'), findsOneWidget);
    expect(
      tester.widget<TextField>(find.byType(TextField).at(0)).controller?.text,
      'custom',
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('添加中退出再进入会丢掉错误并重新拉列表', (tester) async {
    var lists = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (method == 'POST' && path == '/api/v1/providers') {
              return pending.future;
            }
            lists++;
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
    await tester.pump();
    await tester.enterText(find.byType(TextField).at(0), 'custom');
    await tester.tap(find.text('添加供应商'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开供应商'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: DynamicProviderPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('自定义 GLM'), findsOneWidget);
    expect(lists, 2);
    expect(tester.takeException(), isNull);
  });

  testWidgets('停用网络断开显示失败原文', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('/toggle')) {
              expect(path, '/api/v1/providers/p1/toggle');
              expect(method, 'PUT');
              throw const SocketException('connection lost');
            }
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
    await tester.pump();
    await tester.ensureVisible(find.byType(PopupMenuButton<String>));
    await tester.tap(find.byType(PopupMenuButton<String>));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('停用'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('自定义 GLM'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('停用进行中无法再次打开菜单触发并发操作', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var toggles = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('/toggle')) {
              toggles++;
              return pending.future;
            }
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
    await tester.pump();
    await tester.ensureVisible(find.byType(PopupMenuButton<String>));
    await tester.tap(find.byType(PopupMenuButton<String>));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('停用'));
    await tester.pump();
    expect(toggles, 1);
    await tester.tap(find.byType(PopupMenuButton<String>));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.byType(PopupMenuItem<String>), findsNothing);
    expect(toggles, 1);
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('停用中退出再进入会丢掉错误并重新拉列表', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var lists = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('/toggle')) return pending.future;
            lists++;
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
    await tester.pump();
    await tester.ensureVisible(find.byType(PopupMenuButton<String>));
    await tester.tap(find.byType(PopupMenuButton<String>));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('停用'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开供应商'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: DynamicProviderPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('自定义 GLM'), findsOneWidget);
    expect(lists, 2);
    expect(tester.takeException(), isNull);
  });

  testWidgets('同步模型网络断开显示失败原文', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('/sync')) {
              expect(path, '/api/v1/providers/p1/sync?force=true');
              expect(method, 'POST');
              throw const SocketException('connection lost');
            }
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
    await tester.pump();
    await tester.tap(find.byType(PopupMenuButton<String>));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('同步模型'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('同步中退出再进入会丢掉错误并重新拉列表', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var lists = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('/sync')) return pending.future;
            lists++;
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
    await tester.pump();
    await tester.tap(find.byType(PopupMenuButton<String>));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('同步模型'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开供应商'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: DynamicProviderPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('自定义 GLM'), findsOneWidget);
    expect(lists, 2);
    expect(tester.takeException(), isNull);
  });

  testWidgets('测试连接网络断开显示失败原文', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('/test')) {
              expect(path, '/api/v1/providers/p1/test');
              expect(method, 'POST');
              throw const SocketException('connection lost');
            }
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
    await tester.pump();
    await tester.tap(find.byType(PopupMenuButton<String>));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('测试连接'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('测试连接中退出再进入会丢掉错误并重新拉列表', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var lists = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('/test')) return pending.future;
            lists++;
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
    await tester.pump();
    await tester.tap(find.byType(PopupMenuButton<String>));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('测试连接'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开供应商'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: DynamicProviderPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('自定义 GLM'), findsOneWidget);
    expect(lists, 2);
    expect(tester.takeException(), isNull);
  });

  testWidgets('删除网络断开显示失败原文', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (method == 'DELETE') {
              expect(path, '/api/v1/providers/p1');
              throw const SocketException('connection lost');
            }
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
    await tester.pump();
    await tester.tap(find.byType(PopupMenuButton<String>));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('删除'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('自定义 GLM'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('删除中退出再进入会丢掉错误并重新拉列表', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var lists = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (method == 'DELETE') return pending.future;
            lists++;
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
    await tester.pump();
    await tester.tap(find.byType(PopupMenuButton<String>));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('删除'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开供应商'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: DynamicProviderPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('自定义 GLM'), findsOneWidget);
    expect(lists, 2);
    expect(tester.takeException(), isNull);
  });
}
