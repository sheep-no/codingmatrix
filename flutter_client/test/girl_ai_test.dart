import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/application/girl_ai_controller.dart';
import 'package:codingmatrix_desktop/presentation/virtual_girl_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'agent_delivery_test.dart' show DeliveryApi;

class GirlApi extends DeliveryApi {
  GirlApi(super.handle);
}

Map<String, dynamic> turnReply({String text = '嗨'}) => {
  'assistant_text': text,
  'turn_id': 't1',
  'emotion': {'label': 'happy'},
  'intent': {'label': 'chat'},
};

void main() {
  late GirlApi api;
  late ProviderContainer container;

  setUp(() {
    api = GirlApi((path, method, body) async {
      if (path == '/api/v1/GirlAi/characters') {
        return {
          'characters': [
            {'id': 'gentle', 'name': '温柔'},
          ],
        };
      }
      if (path == '/api/v1/GirlAi/companion/turn') {
        expect(method, 'POST');
        expect(body, {'prompt': '你好', 'character_id': 'gentle'});
        return turnReply();
      }
      fail('unexpected $path');
    });
    container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
  });
  tearDown(() => container.dispose());

  test('发送后写入助手回复和情绪', () async {
    await container.read(girlAiControllerProvider.notifier).send('你好');
    final state = container.read(girlAiControllerProvider);
    expect(state.messages.map((message) => message.content), ['你好', '嗨']);
    expect(state.emotion?.label, 'happy');
    expect(state.intent?.label, 'chat');
    expect(state.loading, false);
  });

  test('发送中网络断开保留用户原文并显示错误', () async {
    api = GirlApi(
      (_, __, ___) async => throw const SocketException('connection lost'),
    );
    container.dispose();
    container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    await container.read(girlAiControllerProvider.notifier).send('你好');
    final state = container.read(girlAiControllerProvider);
    expect(state.error, contains('connection lost'));
    expect(state.loading, false);
    expect(state.messages.single.content, '你好');
  });

  testWidgets('发送完成后退出再进入仍显示对话', (tester) async {
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: VirtualGirlPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('温柔'), findsOneWidget);

    await tester.enterText(find.byType(TextField), '你好');
    await tester.tap(find.byIcon(Icons.send));
    await tester.pump();
    await tester.pump();
    expect(find.text('你好'), findsOneWidget);
    expect(find.text('嗨'), findsOneWidget);
    expect(find.text('情绪: happy'), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开虚拟姬'))),
      ),
    );
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: VirtualGirlPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('你好'), findsOneWidget);
    expect(find.text('嗨'), findsOneWidget);
  });

  testWidgets('发送中退出再进入会丢掉晚到的回复', (tester) async {
    final pending = Completer<Object?>();
    api = GirlApi((path, method, body) async {
      if (path == '/api/v1/GirlAi/characters') {
        return {
          'characters': [
            {'id': 'gentle', 'name': '温柔'},
          ],
        };
      }
      if (path == '/api/v1/GirlAi/companion/turn') {
        return pending.future;
      }
      fail('unexpected $path');
    });
    container.dispose();
    container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: VirtualGirlPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.enterText(find.byType(TextField), '你好');
    await tester.tap(find.byIcon(Icons.send));
    await tester.pump();
    expect(find.text('你好'), findsOneWidget);
    expect(container.read(girlAiControllerProvider).loading, true);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开虚拟姬'))),
      ),
    );
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: VirtualGirlPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    pending.complete(turnReply(text: '不应出现'));
    await tester.pump();
    expect(find.text('你好'), findsOneWidget);
    expect(find.text('不应出现'), findsNothing);
  });
}
