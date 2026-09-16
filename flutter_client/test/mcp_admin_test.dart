import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/infrastructure/mcp/mcp_admin_client.dart';
import 'package:codingmatrix_desktop/presentation/mcp_admin_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'agent_delivery_test.dart' show DeliveryApi;
import 'auth_session_test.dart' show Fixture;
import 'module_lifecycle_test.dart' show ModuleAuth;

const serverItem = {
  'name': 'filesystem',
  'transport': 'stdio',
  'description': '本地文件',
  'enabled': true,
};

void main() {
  test('列出 MCP 服务解析 servers 字段', () async {
    final client = McpAdminClient(
      DeliveryApi((path, method, body) async {
        expect(path, '/api/v2/mcp/servers');
        expect(method, 'GET');
        return {
          'servers': [serverItem],
        };
      }),
    );
    final items = await client.listServers();
    expect(items.single['name'], 'filesystem');
    expect(items.single['enabled'], isTrue);
  });

  test('列出 MCP 服务网络断开会失败', () async {
    final client = McpAdminClient(
      DeliveryApi(
        (_, __, ___) async => throw const SocketException('connection lost'),
      ),
    );
    await expectLater(
      client.listServers(),
      throwsA(
        isA<SocketException>().having(
          (error) => error.message,
          'message',
          'connection lost',
        ),
      ),
    );
  });

  testWidgets('加载后显示已启用的 MCP 服务', (tester) async {
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi(
            (_, __, ___) async => {
              'servers': [serverItem],
            },
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('filesystem'), findsOneWidget);
    expect(find.textContaining('stdio'), findsWidgets);
  });

  testWidgets('切换账号清空表单并重新拉取新账号的服务', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    var calls = 0;
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((_, __, ___) async {
            calls++;
            if (calls == 1) {
              return {
                'servers': [serverItem],
              };
            }
            return {'servers': []};
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('filesystem'), findsOneWidget);
    expect(calls, 1);

    final nameField = find.byWidgetPredicate(
      (w) => w is TextField && w.decoration?.labelText == '名称',
    );
    await tester.enterText(nameField, 'alice-mcp-server');
    expect(find.text('alice-mcp-server'), findsOneWidget);

    auth.switchAccount('bob');
    await tester.pump();
    await tester.pump();

    expect(find.text('alice-mcp-server'), findsNothing);
    expect(find.text('filesystem'), findsNothing);
    expect(calls, 2);
    expect(tester.takeException(), isNull);
  });

  testWidgets('切换账号后旧账号的服务列表不会覆盖新列表', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final pending = Completer<Object?>();
    var calls = 0;
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((_, __, ___) async {
            calls++;
            if (calls == 1) return pending.future;
            return {'servers': []};
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();

    auth.switchAccount('bob');
    await tester.pump();
    await tester.pump();
    expect(find.text('filesystem'), findsNothing);

    pending.complete({
      'servers': [serverItem],
    });
    await tester.pump();
    await tester.pump();

    expect(find.text('filesystem'), findsNothing);
    expect(calls, 2);
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
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('MCP 服务读取失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('filesystem'), findsNothing);
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
              'servers': [serverItem],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    expect(find.byType(LinearProgressIndicator), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 MCP'))),
      ),
    );
    await tester.pump();
    pending.complete({
      'servers': [
        {
          'name': '旧服务',
          'transport': 'http',
          'description': '应丢弃',
          'enabled': false,
        },
      ],
    });
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('filesystem'), findsOneWidget);
    expect(find.text('旧服务'), findsNothing);
    expect(calls, 2);
  });

  testWidgets('添加网络断开显示失败原文', (tester) async {
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            if (method == 'POST' && path == '/api/v2/mcp/servers') {
              expect(body, {
                'name': 'browser',
                'transport': 'stdio',
                'enabled': true,
              });
              throw const SocketException('connection lost');
            }
            return {
              'servers': [serverItem],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.enterText(find.byType(TextField).first, 'browser');
    await tester.tap(find.text('添加'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('MCP 服务添加失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('filesystem'), findsOneWidget);
    expect(
      tester.widget<TextField>(find.byType(TextField).first).controller?.text,
      'browser',
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
            if (method == 'POST' && path == '/api/v2/mcp/servers') {
              return pending.future;
            }
            lists++;
            return {
              'servers': [serverItem],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.enterText(find.byType(TextField).first, 'browser');
    await tester.tap(find.text('添加'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 MCP'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('MCP 服务添加失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('filesystem'), findsOneWidget);
    expect(lists, 2);
    expect(tester.takeException(), isNull);
  });

  testWidgets('启停网络断开显示失败原文', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('/toggle')) {
              expect(path, '/api/v2/mcp/servers/filesystem/toggle');
              expect(method, 'POST');
              throw const SocketException('connection lost');
            }
            return {
              'servers': [serverItem],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('启停'));
    await tester.tap(find.byTooltip('启停'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('MCP 服务状态更新失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('启停进行中无法再次触发并发请求', (tester) async {
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
            return {
              'servers': [serverItem],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('启停'));
    await tester.tap(find.byTooltip('启停'));
    await tester.pump();
    expect(toggles, 1);
    await tester.ensureVisible(find.byTooltip('启停'));
    await tester.tap(find.byTooltip('启停'));
    await tester.pump();
    expect(toggles, 1);
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('启停中退出再进入会丢掉错误并重新拉列表', (tester) async {
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
            return {
              'servers': [serverItem],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('启停'));
    await tester.tap(find.byTooltip('启停'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 MCP'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('MCP 服务状态更新失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('filesystem'), findsOneWidget);
    expect(lists, 2);
    expect(tester.takeException(), isNull);
  });

  testWidgets('切账号后旧账号的连接测试弹层不会弹出', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, _, __) async {
            if (path.contains('/test')) return pending.future;
            return {
              'servers': [serverItem],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('连接测试'));
    await tester.tap(find.byTooltip('连接测试'));
    await tester.pump();

    auth.switchAccount('bob');
    await tester.pump();
    await tester.pump();

    pending.complete({'ok': true, 'detail': '上一账号的测试结果'});
    await tester.pumpAndSettle();

    expect(find.byType(AlertDialog), findsNothing);
    expect(find.textContaining('上一账号的测试结果'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('连接测试网络断开显示失败原文', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('/test')) {
              expect(path, '/api/v2/mcp/servers/filesystem/test');
              expect(method, 'POST');
              throw const SocketException('connection lost');
            }
            return {
              'servers': [serverItem],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('连接测试'));
    await tester.tap(find.byTooltip('连接测试'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('连接测试失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('连接测试中退出再进入会丢掉错误并重新拉列表', (tester) async {
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
            return {
              'servers': [serverItem],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('连接测试'));
    await tester.tap(find.byTooltip('连接测试'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 MCP'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('连接测试失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('filesystem'), findsOneWidget);
    expect(lists, 2);
    expect(tester.takeException(), isNull);
  });

  testWidgets('取消编辑会释放临时输入控制器', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi(
            (_, __, ___) async => {
              'servers': [serverItem],
            },
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('编辑'));
    await tester.tap(find.byTooltip('编辑'));
    await tester.pump();

    final controllers = tester
        .widgetList<TextField>(
          find.descendant(
            of: find.byType(AlertDialog),
            matching: find.byType(TextField),
          ),
        )
        .map((field) => field.controller!)
        .toList();
    expect(controllers, isNotEmpty);

    await tester.tap(find.text('取消'));
    await tester.pumpAndSettle();

    for (final controller in controllers) {
      expect(() => controller.addListener(() {}), throwsFlutterError);
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('编辑网络断开显示失败原文', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            if (method == 'PUT') {
              expect(path, '/api/v2/mcp/servers/filesystem');
              expect(body, {'enabled': true, 'command': ''});
              throw const SocketException('connection lost');
            }
            return {
              'servers': [serverItem],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('编辑'));
    await tester.tap(find.byTooltip('编辑'));
    await tester.pump();
    await tester.tap(find.text('保存'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('MCP 服务更新失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('编辑中退出再进入会丢掉错误并重新拉列表', (tester) async {
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
            if (method == 'PUT') return pending.future;
            lists++;
            return {
              'servers': [serverItem],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('编辑'));
    await tester.tap(find.byTooltip('编辑'));
    await tester.pump();
    await tester.tap(find.text('保存'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 MCP'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('MCP 服务更新失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('filesystem'), findsOneWidget);
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
              expect(path, '/api/v2/mcp/servers/filesystem');
              throw const SocketException('connection lost');
            }
            return {
              'servers': [serverItem],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('删除'));
    await tester.tap(find.byTooltip('删除'));
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, '删除'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('MCP 服务删除失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('filesystem'), findsOneWidget);
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
            return {
              'servers': [serverItem],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('删除'));
    await tester.tap(find.byTooltip('删除'));
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, '删除'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 MCP'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: McpAdminPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('MCP 服务删除失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('filesystem'), findsOneWidget);
    expect(lists, 2);
    expect(tester.takeException(), isNull);
  });
}
