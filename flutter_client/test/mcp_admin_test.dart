import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/infrastructure/mcp/mcp_admin_client.dart';
import 'package:codingmatrix_desktop/presentation/mcp_admin_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'agent_delivery_test.dart' show DeliveryApi;

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
          DeliveryApi((_, __, ___) async => {
            'servers': [serverItem],
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
    expect(find.textContaining('stdio'), findsWidgets);
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
}
