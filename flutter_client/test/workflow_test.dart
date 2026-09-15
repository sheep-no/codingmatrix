import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/application/workflow_controller.dart';
import 'package:codingmatrix_desktop/infrastructure/workflow/workflow_client.dart';
import 'package:codingmatrix_desktop/presentation/workflow_page.dart';
import 'agent_delivery_test.dart' show DeliveryApi;

const graph = {
  'event': 'task_graph_generated',
  'workflow_id': 'w1',
  'nodes': [
    {
      'id': 'n1',
      'type': 'data_transform',
      'params': {'value': '中文'},
      'depends_on': [],
    },
    {
      'id': 'n2',
      'type': 'chart_generation',
      'depends_on': ['n1'],
    },
  ],
};

class WorkflowApi extends DeliveryApi {
  WorkflowApi(this.bytes, {this.statusResult})
    : super((_, __, ___) async => null);
  final Stream<List<int>> bytes;
  final Future<Object?>? statusResult;
  int posts = 0;
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    posts++;
    expect(request.method, 'POST');
    expect(request.url.path, '/api/v1/workflow/execute');
    expect(request.headers['Accept'], 'application/x-ndjson');
    expect(jsonDecode((request as http.Request).body), {
      'natural_language_request': '任务',
      'timeout': 1800,
      'export_workflow': false,
    });
    return http.StreamedResponse(bytes, 200);
  }

  @override
  Future<Object?> requestJson(
    String path, {
    String method = 'GET',
    Object? body,
    Duration? timeout,
  }) {
    expect(path, '/api/v1/workflow/status/w1');
    expect(method, 'GET');
    return statusResult ??
        Future.value({
          'workflow_id': 'w1',
          'status': 'completed',
          'task_graph': {'nodes': graph['nodes']},
          'summary': {'completed_nodes': 2},
        });
  }
}

List<int> line(Map<String, Object?> event) =>
    utf8.encode('${jsonEncode(event)}\n');
Future<void> tick() => Future<void>.delayed(Duration.zero);

class ThrowingSendApi extends DeliveryApi {
  ThrowingSendApi() : super((_, __, ___) async => null);
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    throw const SocketException('connection lost');
  }
}

void main() {
  test(
    'NDJSON handles split UTF8, CRLF, blank lines and final unterminated event',
    () async {
      final bytes = utf8.encode(
        '${jsonEncode(graph)}\r\n\n{"event":"workflow_completed","status":"completed"}',
      );
      final events = await WorkflowClient.parse(
        Stream.fromIterable(bytes.map((b) => [b])),
      ).toList();
      expect(events.length, 2);
      expect(events.first['nodes'], graph['nodes']);
    },
  );
  test('NDJSON rejects malformed and oversized records', () async {
    for (final text in ['{"broken":', '{}', 'x' * (1024 * 1024 + 1)]) {
      await expectLater(
        WorkflowClient.parse(Stream.value(utf8.encode(text))).drain<void>(),
        throwsFormatException,
      );
    }
  });
  test(
    'incremental nodes and terminal result absorb late events with one POST',
    () async {
      final source = StreamController<List<int>>();
      final api = WorkflowApi(source.stream);
      final controller = WorkflowController(WorkflowClient(api));
      await controller.execute('任务');
      await controller.execute('任务');
      expect(api.posts, 1);
      source.add(line(graph));
      source.add(line({'event': 'node_started', 'node_id': 'n1'}));
      await tick();
      expect(controller.state.snapshot.nodes.first.status, 'running');
      source.add(
        line({
          'event': 'node_completed',
          'node_id': 'n1',
          'success': true,
          'data': {'value': 3},
        }),
      );
      await tick();
      expect(controller.state.snapshot.nodes.first.result, {'value': 3});
      source.add(
        line({
          'event': 'workflow_completed',
          'status': 'failed',
          'summary': {'failed_nodes': 1},
        }),
      );
      source.add(line({'event': 'node_started', 'node_id': 'n1'}));
      await tick();
      expect(controller.state.active, false);
      expect(controller.state.snapshot.status, 'failed');
      expect(controller.state.snapshot.nodes.first.status, 'completed');
      await source.close();
      controller.dispose();
    },
  );
  test(
    'local disconnect preserves graph and status recovers without POST',
    () async {
      final source = StreamController<List<int>>();
      final api = WorkflowApi(source.stream);
      final controller = WorkflowController(WorkflowClient(api));
      await controller.execute('任务');
      source.add(line(graph));
      await tick();
      await controller.disconnect();
      expect(controller.state.snapshot.id, 'w1');
      expect(controller.state.snapshot.status, 'disconnected');
      await controller.refresh();
      expect(controller.state.snapshot.status, 'completed');
      expect(api.posts, 1);
      controller.dispose();
      await source.close();
    },
  );
  test(
    'early EOF is disconnected; late status after disposal is ignored',
    () async {
      final pending = Completer<Object?>();
      final controller = WorkflowController(
        WorkflowClient(
          WorkflowApi(Stream.value(line(graph)), statusResult: pending.future),
        ),
      );
      await controller.execute('任务');
      await tick();
      expect(controller.state.snapshot.status, 'disconnected');
      final refresh = controller.refresh();
      controller.dispose();
      pending.complete({'workflow_id': 'w1', 'status': 'completed'});
      await refresh;
    },
  );
  test('local disconnect survives a stream that fails to cancel', () async {
    final source = StreamController<List<int>>(
      onCancel: () => throw const SocketException('connection lost'),
    );
    final api = WorkflowApi(source.stream);
    final controller = WorkflowController(WorkflowClient(api));
    await controller.execute('任务');
    await tick();
    await controller.disconnect();
    expect(controller.state.snapshot.status, 'disconnected');
    controller.dispose();
  });
  testWidgets(
    'compact workflow renders dependencies, errors and local disconnect',
    (tester) async {
      tester.view.physicalSize = const Size(360, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final source = StreamController<List<int>>();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            workflowControllerProvider.overrideWith(
              (_) => WorkflowController(
                WorkflowClient(WorkflowApi(source.stream)),
              ),
            ),
          ],
          child: const MaterialApp(home: WorkflowPage()),
        ),
      );
      await tester.enterText(find.byKey(const Key('workflowInput')), '任务');
      await tester.tap(find.byKey(const Key('workflowExecute')));
      await tester.pump();
      source.add(line(graph));
      await tester.pump();
      await tester.pump();
      expect(find.text('依赖：n1'), findsOneWidget);
      await tester.tap(find.text('断开本地连接'));
      await tester.pumpAndSettle();
      expect(find.textContaining('本地连接已断开'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
      expect(source.hasListener, false);
      unawaited(source.close());
      await tester.pump();
    },
  );

  testWidgets('空任务不会发起执行', (tester) async {
    final container = ProviderContainer(
      overrides: [
        workflowControllerProvider.overrideWith(
          (_) => WorkflowController(WorkflowClient(ThrowingSendApi())),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: WorkflowPage()),
      ),
    );
    await tester.tap(find.byKey(const Key('workflowExecute')));
    await tester.pump();
    expect(find.text('请输入任务描述'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsNothing);
  });

  testWidgets('执行请求网络断开显示未知结果', (tester) async {
    final container = ProviderContainer(
      overrides: [
        workflowControllerProvider.overrideWith(
          (_) => WorkflowController(WorkflowClient(ThrowingSendApi())),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: WorkflowPage()),
      ),
    );
    await tester.enterText(find.byKey(const Key('workflowInput')), '任务');
    await tester.tap(find.byKey(const Key('workflowExecute')));
    await tester.pump();
    await tester.pump();
    expect(find.text('执行请求失败或结果未知，请先核对任务状态'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.byType(LinearProgressIndicator), findsNothing);
  });

  testWidgets('执行中退出再进入不会保留任务图', (tester) async {
    final source = StreamController<List<int>>();
    addTearDown(() {
      unawaited(source.close());
    });
    final api = WorkflowApi(source.stream);
    final container = ProviderContainer(
      overrides: [
        workflowControllerProvider.overrideWith(
          (_) => WorkflowController(WorkflowClient(api)),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: WorkflowPage()),
      ),
    );
    await tester.enterText(find.byKey(const Key('workflowInput')), '任务');
    await tester.tap(find.byKey(const Key('workflowExecute')));
    await tester.pump();
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    expect(find.text('状态：connecting'), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开工作流'))),
      ),
    );
    await tester.pump();
    expect(source.hasListener, false);
    try {
      source.add(line(graph));
    } on StateError catch (_) {}
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: WorkflowPage()),
      ),
    );
    await tester.pump();
    expect(find.text('状态：idle'), findsOneWidget);
    expect(find.text('依赖：n1'), findsNothing);
    expect(
      tester
          .widget<TextFormField>(find.byKey(const Key('workflowInput')))
          .controller
          ?.text,
      isEmpty,
    );
  });

  test('读取历史网络断开会失败', () async {
    final api = DeliveryApi(
      (_, __, ___) async => throw const SocketException('connection lost'),
    );
    await expectLater(
      WorkflowClient(api).history(),
      throwsA(
        isA<SocketException>().having(
          (error) => error.message,
          'message',
          'connection lost',
        ),
      ),
    );
  });

  test('删除历史网络断开会失败', () async {
    final api = DeliveryApi((path, method, body) async {
      expect(path, '/api/v1/workflow/history/w1');
      expect(method, 'DELETE');
      throw const SocketException('connection lost');
    });
    await expectLater(
      WorkflowClient(api).deleteHistory('w1'),
      throwsA(
        isA<SocketException>().having(
          (error) => error.message,
          'message',
          'connection lost',
        ),
      ),
    );
  });

  Future<ProviderContainer> pumpWorkflow(
    WidgetTester tester,
    DeliveryApi api,
  ) async {
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(api),
        workflowControllerProvider.overrideWith(
          (_) => WorkflowController(WorkflowClient(api)),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: WorkflowPage()),
      ),
    );
    return container;
  }

  Future<void> submitImport(WidgetTester tester) async {
    await tester.tap(find.text('导入工作流'));
    await tester.pump();
    await tester.pump();
    await tester.enterText(
      find.descendant(
        of: find.byType(AlertDialog),
        matching: find.byType(TextField),
      ),
      '{"nodes":[]}',
    );
    await tester.tap(find.text('导入'));
    await tester.pump();
    await tester.pump();
  }

  testWidgets('导入工作流网络断开显示失败原文', (tester) async {
    final api = DeliveryApi((path, method, body) async {
      expect(path, '/api/v1/workflow/import');
      expect(method, 'POST');
      expect(body, {'nodes': []});
      throw const SocketException('connection lost');
    });
    await pumpWorkflow(tester, api);
    await submitImport(tester);
    expect(find.textContaining('导入失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('导入中退出再进入会丢掉错误', (tester) async {
    final pending = Completer<Object?>();
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/workflow/import') return pending.future;
      fail('unexpected $path');
    });
    final container = await pumpWorkflow(tester, api);
    await submitImport(tester);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          key: UniqueKey(),
          home: const Scaffold(body: Text('离开工作流')),
        ),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          key: UniqueKey(),
          home: const WorkflowPage(),
        ),
      ),
    );
    await tester.pump();
    expect(find.textContaining('导入失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  DeliveryApi streamingApi(
    Stream<List<int>> bytes,
    Future<Object?> Function(String, String, Object?) json,
  ) => DeliveryApi(
    json,
    sendHandle: (request) async {
      expect(request.url.path, '/api/v1/workflow/execute');
      return http.StreamedResponse(bytes, 200);
    },
  );

  Future<void> executeUntilId(
    WidgetTester tester,
    StreamController<List<int>> source,
  ) async {
    await tester.enterText(find.byKey(const Key('workflowInput')), '任务');
    await tester.tap(find.byKey(const Key('workflowExecute')));
    await tester.pump();
    source.add(line(graph));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('工作流 ID：w1'), findsOneWidget);
  }

  testWidgets('导出工作流网络断开显示失败原文', (tester) async {
    final source = StreamController<List<int>>();
    addTearDown(() {
      unawaited(source.close());
    });
    final api = streamingApi(source.stream, (path, method, body) async {
      expect(path, '/api/v1/workflow/export/w1');
      expect(method, 'GET');
      throw const SocketException('connection lost');
    });
    await pumpWorkflow(tester, api);
    await executeUntilId(tester, source);
    await tester.ensureVisible(find.text('导出工作流'));
    await tester.tap(find.text('导出工作流'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('导出失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('工作流导出'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('导出中退出再进入会丢掉错误', (tester) async {
    final source = StreamController<List<int>>();
    addTearDown(() {
      unawaited(source.close());
    });
    final pending = Completer<Object?>();
    final api = streamingApi(source.stream, (path, _, __) async {
      if (path == '/api/v1/workflow/export/w1') return pending.future;
      fail('unexpected $path');
    });
    final container = await pumpWorkflow(tester, api);
    await executeUntilId(tester, source);
    await tester.ensureVisible(find.text('导出工作流'));
    await tester.tap(find.text('导出工作流'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          key: UniqueKey(),
          home: const Scaffold(body: Text('离开工作流')),
        ),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          key: UniqueKey(),
          home: const WorkflowPage(),
        ),
      ),
    );
    await tester.pump();
    expect(find.textContaining('导出失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.textContaining('工作流 ID：w1'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('查询状态网络断开显示笼统错误', (tester) async {
    final source = StreamController<List<int>>();
    addTearDown(() {
      unawaited(source.close());
    });
    final api = streamingApi(source.stream, (path, method, body) async {
      expect(path, '/api/v1/workflow/status/w1');
      expect(method, 'GET');
      throw const SocketException('connection lost');
    });
    await pumpWorkflow(tester, api);
    await executeUntilId(tester, source);
    await tester.tap(find.text('断开本地连接'));
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.text('查询状态'));
    await tester.tap(find.text('查询状态'));
    await tester.pump();
    await tester.pump();
    expect(find.text('状态查询失败；任务可能已过期或当前服务进程没有记录'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('读取历史网络断开显示失败原文', (tester) async {
    final api = DeliveryApi((path, method, body) async {
      expect(path, '/api/v1/workflow/history');
      expect(method, 'GET');
      throw const SocketException('connection lost');
    });
    await pumpWorkflow(tester, api);
    await tester.tap(find.byIcon(Icons.history));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('历史读取失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('读取历史中退出再进入会丢掉错误', (tester) async {
    final pending = Completer<Object?>();
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/workflow/history') return pending.future;
      fail('unexpected $path');
    });
    final container = await pumpWorkflow(tester, api);
    await tester.tap(find.byIcon(Icons.history));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          key: UniqueKey(),
          home: const Scaffold(body: Text('离开工作流')),
        ),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(key: UniqueKey(), home: const WorkflowPage()),
      ),
    );
    await tester.pump();
    expect(find.textContaining('历史读取失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('删除历史网络断开显示失败原文', (tester) async {
    tester.view.physicalSize = const Size(800, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = DeliveryApi((path, method, body) async {
      if (path == '/api/v1/workflow/history') {
        return {
          'items': [
            {'workflow_id': 'w1', 'name': '历史一', 'status': 'completed'},
          ],
        };
      }
      expect(path, '/api/v1/workflow/history/w1');
      expect(method, 'DELETE');
      throw const SocketException('connection lost');
    });
    await pumpWorkflow(tester, api);
    await tester.tap(find.byIcon(Icons.history));
    await tester.pump();
    await tester.pump();
    expect(find.text('历史一'), findsOneWidget);
    await tester.ensureVisible(find.byTooltip('删除历史'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('删除历史'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('删除失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('删除历史中退出再进入会丢掉错误', (tester) async {
    tester.view.physicalSize = const Size(800, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final pending = Completer<Object?>();
    final api = DeliveryApi((path, method, body) async {
      if (path == '/api/v1/workflow/history') {
        return {
          'items': [
            {'workflow_id': 'w1', 'name': '历史一', 'status': 'completed'},
          ],
        };
      }
      if (path == '/api/v1/workflow/history/w1') return pending.future;
      fail('unexpected $path');
    });
    final container = await pumpWorkflow(tester, api);
    await tester.tap(find.byIcon(Icons.history));
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('删除历史'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('删除历史'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          key: UniqueKey(),
          home: const Scaffold(body: Text('离开工作流')),
        ),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(key: UniqueKey(), home: const WorkflowPage()),
      ),
    );
    await tester.pump();
    expect(find.textContaining('删除失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
