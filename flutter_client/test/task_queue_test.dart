import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/cloud_auth_client.dart';
import 'package:codingmatrix_desktop/infrastructure/task/task_client.dart';
import 'package:codingmatrix_desktop/presentation/task_queue_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'agent_delivery_test.dart' show DeliveryApi;
import 'auth_session_test.dart' show Fixture;
import 'module_lifecycle_test.dart' show ModuleAuth;

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
          DeliveryApi(
            (_, __, ___) async => {
              'tasks': [taskItem],
            },
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
    expect(find.text('ppt · running'), findsOneWidget);
    expect(find.textContaining('生成中'), findsOneWidget);
  });

  testWidgets('切换账号清空旧任务并重新拉列表', (tester) async {
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
                    'tasks': [
                      {
                        'task_id': 'old',
                        'task_type': 'ppt',
                        'status': 'queued',
                        'progress_message': '旧任务',
                      },
                    ],
                  }
                : {
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
    await tester.pump();
    expect(find.textContaining('旧任务'), findsOneWidget);

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    expect(find.textContaining('旧任务'), findsNothing);
    expect(find.textContaining('生成中'), findsOneWidget);
    expect(lists, 2);
  });

  testWidgets('切换账号后旧账号的加载结果不会覆盖新列表', (tester) async {
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

    auth.switchAccount('bob');
    await tester.pump();
    await tester.pump();

    pending.complete({
      'tasks': [
        {
          'task_id': 'old',
          'task_type': 'ppt',
          'status': 'queued',
          'progress_message': '旧任务',
        },
      ],
    });
    await tester.pump();
    await tester.pump();
    await tester.pump();

    expect(find.textContaining('旧任务'), findsNothing);
    expect(find.textContaining('生成中'), findsOneWidget);
    expect(lists, 2);
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

  testWidgets('取消网络断开显示失败原文', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (method == 'DELETE') {
              expect(path, '/api/v1/tasks/t1');
              throw const SocketException('connection lost');
            }
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
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('取消'));
    await tester.tap(find.byTooltip('取消'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('ppt · running'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('取消中退出再进入会丢掉错误', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (method == 'DELETE') return pending.future;
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
    await tester.pump();
    await tester.tap(find.byTooltip('取消'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开任务队列'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: TaskQueuePage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('ppt · running'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('重试进行中无法再次触发并发请求', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    const failed = {
      'task_id': 't2',
      'task_type': 'ppt',
      'status': 'failed',
      'progress': 0,
      'progress_message': '失败',
    };
    var retries = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('/retry')) {
              retries++;
              return pending.future;
            }
            return {
              'tasks': [failed],
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
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('重试'));
    await tester.tap(find.byTooltip('重试'));
    await tester.pump();
    expect(retries, 1);
    await tester.ensureVisible(find.byTooltip('重试'));
    await tester.tap(find.byTooltip('重试'));
    await tester.pump();
    expect(retries, 1);
    pending.complete(null);
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('查看事件进行中无法再次触发并发请求', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var eventCalls = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('/events')) {
              eventCalls++;
              return pending.future;
            }
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
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('查看事件'));
    await tester.tap(find.byTooltip('查看事件'));
    await tester.pump();
    expect(eventCalls, 1);
    await tester.ensureVisible(find.byTooltip('查看事件'));
    await tester.tap(find.byTooltip('查看事件'));
    await tester.pump();
    expect(eventCalls, 1);
    pending.complete(const <Object?>[]);
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('查看事件网络断开显示失败原文', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('/events')) {
              expect(path, '/api/v1/tasks/t1/events');
              throw const SocketException('connection lost');
            }
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
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('查看事件'));
    await tester.tap(find.byTooltip('查看事件'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.textContaining('事件读取失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('查看事件中退出再进入会丢掉错误', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('/events')) return pending.future;
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
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('查看事件'));
    await tester.tap(find.byTooltip('查看事件'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开任务队列'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: TaskQueuePage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('事件读取失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('ppt · running'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('重试网络断开显示失败原文', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    const failed = {
      'task_id': 't2',
      'task_type': 'ppt',
      'status': 'failed',
      'progress': 0,
      'progress_message': '失败',
    };
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('/retry')) {
              expect(path, '/api/v1/tasks/t2/retry');
              expect(method, 'POST');
              throw const SocketException('connection lost');
            }
            return {
              'tasks': [failed],
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
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('重试'));
    await tester.tap(find.byTooltip('重试'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('ppt · failed'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('重试中退出再进入会丢掉错误', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    const failed = {
      'task_id': 't2',
      'task_type': 'ppt',
      'status': 'failed',
      'progress': 0,
      'progress_message': '失败',
    };
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('/retry')) return pending.future;
            return {
              'tasks': [failed],
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
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('重试'));
    await tester.tap(find.byTooltip('重试'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开任务队列'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: TaskQueuePage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('ppt · failed'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test('取消任务的 204 空响应不算失败', () async {
    final f = Fixture();
    await f.login();
    f.business = (request) async {
      expect(request.method, 'DELETE');
      expect(request.url.path, '/api/v1/tasks/t1');
      return http.Response('', 204);
    };

    // The backend cancels with 204 and no body. Decoding that empty body as
    // JSON used to raise "服务响应 JSON 格式错误" even though the cancel had
    // succeeded, so the page reported a failure and kept the stale status.
    await TaskClient(f.api).cancel('t1');
  });

  test('非空但无效的响应体仍是协议错误', () async {
    final f = Fixture();
    await f.login();
    f.business = (_) async => http.Response('not-json', 200);

    await expectLater(
      TaskClient(f.api).cancel('t1'),
      throwsA(
        isA<CloudAuthException>().having(
          (error) => error.message,
          'message',
          '服务响应 JSON 格式错误',
        ),
      ),
    );
  });
}
