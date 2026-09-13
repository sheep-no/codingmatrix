import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/infrastructure/task/task_client.dart';
import 'package:codingmatrix_desktop/presentation/task_queue_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'agent_delivery_test.dart' show DeliveryApi;

const taskItem = {
  'task_id': 't1',
  'task_type': 'ppt',
  'status': 'running',
  'progress': 40,
  'progress_message': '生成中',
};

void main() {
  test('列出任务解析 tasks 字段', () async {
    final client = TaskClient(
      DeliveryApi((path, method, body) async {
        expect(path, '/api/v1/tasks?page=1&page_size=50');
        expect(method, 'GET');
        return {
          'tasks': [taskItem],
        };
      }),
    );
    final items = await client.list();
    expect(items.single['task_id'], 't1');
    expect(items.single['status'], 'running');
  });

  test('列出任务网络断开会失败', () async {
    final client = TaskClient(
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

  testWidgets('加载后显示运行中的任务', (tester) async {
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((_, __, ___) async => {
            'tasks': [taskItem],
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: TaskQueuePage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('ppt · running'), findsOneWidget);
    expect(find.textContaining('生成中'), findsOneWidget);
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
        child: const MaterialApp(home: TaskQueuePage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('ppt · running'), findsNothing);
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
              'tasks': [taskItem],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: TaskQueuePage()),
      ),
    );
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开任务队列'))),
      ),
    );
    await tester.pump();
    pending.complete({
      'tasks': [
        {'task_id': 'old', 'task_type': 'old', 'status': 'failed'},
      ],
    });
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: TaskQueuePage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('ppt · running'), findsOneWidget);
    expect(find.textContaining('old · failed'), findsNothing);
    expect(calls, 2);
  });
}
