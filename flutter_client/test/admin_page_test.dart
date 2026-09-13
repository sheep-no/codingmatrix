import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/presentation/admin_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'agent_delivery_test.dart' show DeliveryApi;

const userItem = {
  'id': 1,
  'username': 'alice',
  'email': 'alice@example.com',
  'permission_level': 'admin',
};

const usersPayload = {
  'total': 1,
  'users': [userItem],
};

void main() {
  testWidgets('进入页面不自动拉取用户', (tester) async {
    var calls = 0;
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((_, __, ___) async {
            calls++;
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.pump();
    expect(calls, 0);
    expect(find.text('alice'), findsNothing);
    expect(find.text('用户管理'), findsOneWidget);
  });

  testWidgets('点击用户管理后显示用户列表', (tester) async {
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            expect(path, '/api/v2/Controller/users?page=1&page_size=50');
            expect(method, 'GET');
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('用户管理'));
    await tester.pump();
    await tester.pump();
    expect(find.text('用户总数：1'), findsOneWidget);
    expect(find.text('alice'), findsOneWidget);
    expect(find.textContaining('alice@example.com'), findsOneWidget);
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
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('用户管理'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('用户列表读取失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('alice'), findsNothing);
  });

  testWidgets('加载中退出再进入需再次点击拉取', (tester) async {
    var calls = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((_, __, ___) async {
            calls++;
            if (calls == 1) return pending.future;
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('用户管理'));
    await tester.pump();
    expect(find.byType(LinearProgressIndicator), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开管理后台'))),
      ),
    );
    await tester.pump();
    pending.complete({
      'total': 1,
      'users': [
        {
          'id': 9,
          'username': '旧用户',
          'email': 'old@example.com',
          'permission_level': 'normal',
        },
      ],
    });
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.pump();
    expect(find.text('旧用户'), findsNothing);
    expect(find.text('alice'), findsNothing);
    expect(calls, 1);

    await tester.tap(find.text('用户管理'));
    await tester.pump();
    await tester.pump();
    expect(find.text('alice'), findsOneWidget);
    expect(find.text('旧用户'), findsNothing);
    expect(calls, 2);
  });
}
