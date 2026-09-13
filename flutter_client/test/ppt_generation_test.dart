import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/infrastructure/ppt/ppt_client.dart';
import 'package:codingmatrix_desktop/presentation/ppt_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'agent_delivery_test.dart' show DeliveryApi;

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
}
