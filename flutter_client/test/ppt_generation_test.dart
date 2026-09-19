import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/infrastructure/ppt/ppt_client.dart';
import 'package:codingmatrix_desktop/presentation/ppt_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'agent_delivery_test.dart' show DeliveryApi;
import 'auth_session_test.dart' show Fixture;
import 'module_lifecycle_test.dart' show ModuleAuth;

void main() {
  test('提交生成任务并在完成后返回 ppt_id', () async {
    final api = DeliveryApi((path, method, body) async {
      if (path == '/api/v1/pptx/generate_task') {
        expect(method, 'POST');
        expect(body, {'topic': '增长', 'output_format': 'pptx'});
        return {'task_id': 't1'};
      }
      if (path == '/api/v1/tasks/t1') {
        return {
          'status': 'completed',
          'result': {'ppt_id': 'p1'},
        };
      }
      fail('unexpected $path');
    });
    final client = PptClient(api);
    final id = await client.generate('增长');
    expect(id, 't1');
    final status = await client.waitForCompletion(id);
    expect(status['result']['ppt_id'], 'p1');
  });

  test('生成请求网络断开会失败', () async {
    final api = DeliveryApi(
      (_, __, ___) async => throw const SocketException('connection lost'),
    );
    await expectLater(
      PptClient(api).generate('增长'),
      throwsA(
        isA<SocketException>().having(
          (error) => error.message,
          'message',
          'connection lost',
        ),
      ),
    );
  });

  testWidgets('生成完成后可以下载', (tester) async {
    final api = DeliveryApi((path, method, body) async {
      if (path == '/api/v1/pptx/generate_task') {
        return {'task_id': 't1'};
      }
      if (path == '/api/v1/tasks/t1') {
        return {
          'status': 'completed',
          'result': {'ppt_id': 'p1'},
        };
      }
      fail('unexpected $path');
    });
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.enterText(find.byType(TextField), '增长');
    await tester.tap(find.text('生成 PPT'));
    await tester.pump();
    await tester.pump();
    expect(find.text('生成完成，可以下载'), findsOneWidget);
    expect(find.text('下载 PPTX'), findsOneWidget);
  });

  testWidgets('生成中网络断开显示失败', (tester) async {
    final api = DeliveryApi(
      (_, __, ___) async => throw const SocketException('connection lost'),
    );
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.enterText(find.byType(TextField), '增长');
    await tester.tap(find.text('生成 PPT'));
    await tester.pump();
    expect(find.textContaining('任务失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('下载 PPTX'), findsNothing);
  });

  testWidgets('生成中退出再进入不会保留结果', (tester) async {
    final pending = Completer<Object?>();
    final api = DeliveryApi((path, method, body) async {
      if (path == '/api/v1/pptx/generate_task') {
        return {'task_id': 't1'};
      }
      if (path == '/api/v1/tasks/t1') {
        return pending.future;
      }
      fail('unexpected $path');
    });
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.enterText(find.byType(TextField), '增长');
    await tester.tap(find.text('生成 PPT'));
    await tester.pump();
    expect(find.textContaining('任务已提交'), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 PPT'))),
      ),
    );
    await tester.pump();

    pending.complete({
      'status': 'completed',
      'result': {'ppt_id': 'p1'},
    });
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.pump();
    expect(find.text('下载 PPTX'), findsNothing);
    expect(find.text('生成完成，可以下载'), findsNothing);
    expect(find.text('生成 PPT'), findsOneWidget);
  });

  testWidgets('下载PPTX网络断开显示失败原文', (tester) async {
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/pptx/generate_task') return {'task_id': 't1'};
      if (path == '/api/v1/tasks/t1') {
        return {
          'status': 'completed',
          'result': {'ppt_id': 'p1'},
        };
      }
      fail('unexpected $path');
    }, sendHandle: (_) async => throw const SocketException('connection lost'));
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.enterText(find.byType(TextField), '增长');
    await tester.tap(find.text('生成 PPT'));
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('下载 PPTX'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('下载失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('下载中退出再进入会丢掉错误', (tester) async {
    final pending = Completer<Never>();
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/pptx/generate_task') return {'task_id': 't1'};
      if (path == '/api/v1/tasks/t1') {
        return {
          'status': 'completed',
          'result': {'ppt_id': 'p1'},
        };
      }
      fail('unexpected $path');
    }, sendHandle: (_) => pending.future);
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.enterText(find.byType(TextField), '增长');
    await tester.tap(find.text('生成 PPT'));
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('下载 PPTX'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 PPT'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.pump();
    expect(find.textContaining('下载失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('下载 PPTX'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('下载PDF网络断开显示失败原文', (tester) async {
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/pptx/generate_task') return {'task_id': 't1'};
      if (path == '/api/v1/tasks/t1') {
        return {
          'status': 'completed',
          'result': {'ppt_id': 'p1'},
        };
      }
      fail('unexpected $path');
    }, sendHandle: (_) async => throw const SocketException('connection lost'));
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.enterText(find.byType(TextField), '增长');
    await tester.tap(find.text('生成 PPT'));
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('下载 PDF'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('PDF 下载失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test('PDF 下载走服务端按需转换的专用端点', () async {
    final urls = <Uri>[];
    final api = DeliveryApi(
      (_, __, ___) async => fail('unexpected requestJson'),
      sendHandle: (request) async {
        urls.add(request.url);
        return http.StreamedResponse(const Stream<List<int>>.empty(), 404);
      },
    );
    await expectLater(
      PptClient(api).download('p1', (_) {}, format: 'pdf'),
      throwsA(isA<StateError>()),
    );
    expect(urls, hasLength(1));
    expect(urls.single.path, '/api/v1/pptx/download/p1/pdf');
    expect(urls.single.query, isEmpty);
  });

  testWidgets('质量报告进行中无法再次触发并发请求', (tester) async {
    var reports = 0;
    final pending = Completer<Object?>();
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/pptx/generate_task') return {'task_id': 't1'};
      if (path == '/api/v1/tasks/t1') {
        return {
          'status': 'completed',
          'result': {'ppt_id': 'p1'},
        };
      }
      if (path == '/api/v1/pptx/t1/quality-report') {
        reports++;
        return pending.future;
      }
      fail('unexpected $path');
    });
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.enterText(find.byType(TextField), '增长');
    await tester.tap(find.text('生成 PPT'));
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('查看质量报告'));
    await tester.pump();
    expect(reports, 1);
    await tester.tap(find.text('查看质量报告'), warnIfMissed: false);
    await tester.pump();
    expect(reports, 1);
    pending.complete({'pages': 3});
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('质量报告网络断开显示失败原文', (tester) async {
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/pptx/generate_task') return {'task_id': 't1'};
      if (path == '/api/v1/tasks/t1') {
        return {
          'status': 'completed',
          'result': {'ppt_id': 'p1'},
        };
      }
      if (path == '/api/v1/pptx/t1/quality-report') {
        throw const SocketException('connection lost');
      }
      fail('unexpected $path');
    });
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.enterText(find.byType(TextField), '增长');
    await tester.tap(find.text('生成 PPT'));
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('查看质量报告'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('质量报告获取失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('切换账号后旧账号的质量报告不会写入新账号', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final pending = Completer<Object?>();
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/pptx/generate_task') return {'task_id': 't1'};
      if (path == '/api/v1/tasks/t1') {
        return {
          'status': 'completed',
          'result': {'ppt_id': 'p1'},
        };
      }
      if (path == '/api/v1/pptx/t1/quality-report') return pending.future;
      fail('unexpected $path');
    });
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        authenticatedClientProvider.overrideWithValue(api),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.enterText(find.byType(TextField), '增长');
    await tester.tap(find.text('生成 PPT'));
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('查看质量报告'));
    await tester.pump();

    auth.switchAccount('bob');
    await tester.pump();
    await tester.pump();

    pending.complete({'grade': 'A'});
    await tester.pump();
    await tester.pump();

    expect(find.text('质量报告'), findsNothing);
    expect(find.textContaining('quality-report'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('质量报告中退出再进入会丢掉错误', (tester) async {
    final pending = Completer<Object?>();
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/pptx/generate_task') return {'task_id': 't1'};
      if (path == '/api/v1/tasks/t1') {
        return {
          'status': 'completed',
          'result': {'ppt_id': 'p1'},
        };
      }
      if (path == '/api/v1/pptx/t1/quality-report') return pending.future;
      fail('unexpected $path');
    });
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.enterText(find.byType(TextField), '增长');
    await tester.tap(find.text('生成 PPT'));
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('查看质量报告'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 PPT'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.pump();
    expect(find.textContaining('质量报告获取失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('查看质量报告'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('历史读取进行中无法再次触发并发请求', (tester) async {
    var historyCalls = 0;
    final pending = Completer<Object?>();
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/pptx/history') {
        historyCalls++;
        return pending.future;
      }
      fail('unexpected $path');
    });
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.tap(find.byIcon(Icons.history));
    await tester.pump();
    expect(historyCalls, 1);
    await tester.tap(find.byIcon(Icons.history), warnIfMissed: false);
    await tester.pump();
    expect(historyCalls, 1);
    pending.complete({
      'records': [
        {'topic': '增长', 'status': 'completed', 'ppt_id': 'p1'},
      ],
    });
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('历史读取网络断开显示失败原文', (tester) async {
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/pptx/history') {
        throw const SocketException('connection lost');
      }
      fail('unexpected $path');
    });
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.tap(find.byIcon(Icons.history));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('历史读取失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('历史读取中退出再进入会丢掉错误', (tester) async {
    final pending = Completer<Object?>();
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/pptx/history') return pending.future;
      fail('unexpected $path');
    });
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.tap(find.byIcon(Icons.history));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 PPT'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.pump();
    expect(find.textContaining('历史读取失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('大纲创建网络断开显示失败原文', (tester) async {
    final api = DeliveryApi((path, method, body) async {
      if (path == '/api/v1/pptx/outlines') {
        expect(method, 'POST');
        expect(body, {'topic': '增长'});
        throw const SocketException('connection lost');
      }
      fail('unexpected $path');
    });
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.enterText(find.byType(TextField), '增长');
    await tester.tap(find.text('先生成 PPT 大纲'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('大纲创建失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('大纲创建中退出再进入会丢掉错误', (tester) async {
    final pending = Completer<Object?>();
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/pptx/outlines') return pending.future;
      fail('unexpected $path');
    });
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.enterText(find.byType(TextField), '增长');
    await tester.tap(find.text('先生成 PPT 大纲'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 PPT'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.pump();
    expect(find.textContaining('大纲创建失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  Future<ProviderContainer> openOutlineDialog(
    WidgetTester tester,
    DeliveryApi api,
  ) async {
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: PptPage()),
      ),
    );
    await tester.enterText(find.byType(TextField), '增长');
    await tester.tap(find.text('先生成 PPT 大纲'));
    await tester.pump();
    await tester.pump();
    expect(find.text('PPT 大纲'), findsOneWidget);
    return container;
  }

  test('批准大纲网络断开会失败', () async {
    final api = DeliveryApi((path, method, body) async {
      if (path == '/api/v1/pptx/outlines/o1/approve') {
        expect(method, 'POST');
        throw const SocketException('connection lost');
      }
      fail('unexpected $path');
    });
    await expectLater(
      PptClient(api).approveOutline('o1'),
      throwsA(
        isA<SocketException>().having(
          (error) => error.message,
          'message',
          'connection lost',
        ),
      ),
    );
  });

  test('历史读取解析后端 records 字段', () async {
    final api = DeliveryApi((path, method, _) async {
      expect(path, '/api/v1/pptx/history');
      expect(method, 'GET');
      return {
        'records': [
          {'task_id': 'p1', 'title': '增长', 'status': 'completed'},
        ],
        'total': 1,
      };
    });
    final items = await PptClient(api).history();
    expect(items.single['task_id'], 'p1');
  });

  test('大纲创建提交 topic 字段而不是 prompt', () async {
    final api = DeliveryApi((path, method, body) async {
      expect(path, '/api/v1/pptx/outlines');
      expect(method, 'POST');
      expect(body, {'topic': '增长'});
      return {'outline_id': 'o1'};
    });
    final result = await PptClient(api).createOutline('增长');
    expect(result['outline_id'], 'o1');
  });

  test('按大纲生成网络断开会失败', () async {
    final api = DeliveryApi((path, method, body) async {
      if (path == '/api/v1/pptx/outlines/o1/generate') {
        expect(method, 'POST');
        expect(body, {'quality_mode': 'standard'});
        throw const SocketException('connection lost');
      }
      fail('unexpected $path');
    });
    await expectLater(
      PptClient(api).generateFromOutline('o1'),
      throwsA(
        isA<SocketException>().having(
          (error) => error.message,
          'message',
          'connection lost',
        ),
      ),
    );
  });

  testWidgets('批准并生成进行中无法再次触发并发请求', (tester) async {
    var approves = 0;
    final pending = Completer<Object?>();
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/pptx/outlines') {
        return {'outline_id': 'o1'};
      }
      if (path == '/api/v1/pptx/outlines/o1/approve') {
        approves++;
        return pending.future;
      }
      if (path == '/api/v1/pptx/outlines/o1/generate') {
        return {'task_id': 't9'};
      }
      fail('unexpected $path');
    });
    await openOutlineDialog(tester, api);
    await tester.tap(find.text('批准并生成'));
    await tester.pump();
    expect(approves, 1);
    await tester.tap(find.text('批准并生成'), warnIfMissed: false);
    await tester.pump();
    expect(approves, 1);
    pending.complete({'ok': true});
    await tester.pump();
    await tester.pump();
    expect(find.text('PPT 大纲'), findsNothing);
    expect(find.text('已按大纲提交生成：t9'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('批准并生成成功后关闭对话框并显示任务号', (tester) async {
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/pptx/outlines') {
        return {
          'outline_id': 'o1',
          'slides': ['封面'],
        };
      }
      if (path == '/api/v1/pptx/outlines/o1/approve') {
        return {'ok': true};
      }
      if (path == '/api/v1/pptx/outlines/o1/generate') {
        return {'task_id': 't9'};
      }
      fail('unexpected $path');
    });
    await openOutlineDialog(tester, api);
    await tester.tap(find.text('批准并生成'));
    await tester.pump();
    await tester.pump();
    expect(find.text('PPT 大纲'), findsNothing);
    expect(find.text('已按大纲提交生成：t9'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('批准并生成网络断开显示失败原文', (tester) async {
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/pptx/outlines') {
        return {'outline_id': 'o1'};
      }
      if (path == '/api/v1/pptx/outlines/o1/approve') {
        throw const SocketException('connection lost');
      }
      fail('unexpected $path');
    });
    await openOutlineDialog(tester, api);
    await tester.tap(find.text('批准并生成'));
    await tester.pump();
    await tester.pump();
    expect(find.text('PPT 大纲'), findsNothing);
    expect(find.textContaining('生成提交失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('批准并生成中退出再进入会丢掉错误', (tester) async {
    final pending = Completer<Object?>();
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/pptx/outlines') {
        return {'outline_id': 'o1'};
      }
      if (path == '/api/v1/pptx/outlines/o1/approve') return pending.future;
      fail('unexpected $path');
    });
    final container = await openOutlineDialog(tester, api);
    await tester.tap(find.text('批准并生成'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          key: UniqueKey(),
          home: const Scaffold(body: Text('离开 PPT')),
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
        child: MaterialApp(key: UniqueKey(), home: const PptPage()),
      ),
    );
    await tester.pump();
    expect(find.textContaining('生成提交失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('大纲对话框打开后退出再进入会丢掉对话框', (tester) async {
    final api = DeliveryApi((path, _, __) async {
      if (path == '/api/v1/pptx/outlines') {
        return {'outline_id': 'o1'};
      }
      fail('unexpected $path');
    });
    final container = await openOutlineDialog(tester, api);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          key: UniqueKey(),
          home: const Scaffold(body: Text('离开 PPT')),
        ),
      ),
    );
    await tester.pump();
    expect(find.text('PPT 大纲'), findsNothing);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(key: UniqueKey(), home: const PptPage()),
      ),
    );
    await tester.pump();
    expect(find.text('PPT 大纲'), findsNothing);
    expect(find.textContaining('已按大纲提交生成'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
