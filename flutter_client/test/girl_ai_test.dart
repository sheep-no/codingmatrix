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

const memoryJson = {'id': 'm1', 'key': '喜欢', 'value': '猫'};

Map<String, dynamic> turnReplyWithMemory({String text = '嗨'}) => {
  ...turnReply(text: text),
  'memory_candidates': [memoryJson],
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

  testWidgets('发送中网络断开显示错误原文', (tester) async {
    api = GirlApi((path, _, __) async {
      if (path == '/api/v1/GirlAi/characters') {
        return {
          'characters': [
            {'id': 'gentle', 'name': '温柔'},
          ],
        };
      }
      if (path == '/api/v1/GirlAi/companion/turn') {
        throw const SocketException('connection lost');
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
    await tester.pump();
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('你好'), findsOneWidget);
    expect(find.text('嗨'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('发送中退出再进入会丢掉错误但保留用户原文', (tester) async {
    final pending = Completer<Object?>();
    api = GirlApi((path, _, __) async {
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

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开虚拟姬'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
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
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('嗨'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('角色加载网络断开显示错误原文', (tester) async {
    api = GirlApi(
      (_, __, ___) async => throw const SocketException('connection lost'),
    );
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
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('温柔'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('角色加载中退出再进入会丢掉错误', (tester) async {
    var calls = 0;
    final pending = Completer<Object?>();
    api = GirlApi((path, _, __) async {
      if (path == '/api/v1/GirlAi/characters') {
        calls++;
        if (calls == 1) return pending.future;
        return {
          'characters': [
            {'id': 'gentle', 'name': '温柔'},
          ],
        };
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

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开虚拟姬'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: VirtualGirlPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('温柔'), findsOneWidget);
    expect(calls, 2);
    expect(tester.takeException(), isNull);
  });

  testWidgets('历史记录网络断开显示错误原文', (tester) async {
    api = GirlApi((path, _, __) async {
      if (path == '/api/v1/GirlAi/characters') {
        return {
          'characters': [
            {'id': 'gentle', 'name': '温柔'},
          ],
        };
      }
      if (path == '/api/v1/GirlAi/history') {
        throw const SocketException('connection lost');
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
    await tester.tap(find.byTooltip('历史记录'));
    await tester.pump();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('暂无历史记录'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('历史读取中退出再进入会丢掉错误', (tester) async {
    var historyCalls = 0;
    final pending = Completer<Object?>();
    api = GirlApi((path, _, __) async {
      if (path == '/api/v1/GirlAi/characters') {
        return {
          'characters': [
            {'id': 'gentle', 'name': '温柔'},
          ],
        };
      }
      if (path == '/api/v1/GirlAi/history') {
        historyCalls++;
        if (historyCalls == 1) return pending.future;
        return {'records': []};
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
    await tester.tap(find.byTooltip('历史记录'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          key: UniqueKey(),
          home: const Scaffold(body: Text('离开虚拟姬')),
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
          home: const VirtualGirlPage(),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byTooltip('历史记录'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('暂无历史记录'), findsOneWidget);
    expect(historyCalls, 2);
    expect(tester.takeException(), isNull);
  });

  GirlApi memoryApi({
    Future<Object?> Function()? onConfirm,
    Future<Object?> Function()? onDelete,
  }) => GirlApi((path, method, body) async {
    if (path == '/api/v1/GirlAi/characters') {
      return {
        'characters': [
          {'id': 'gentle', 'name': '温柔'},
        ],
      };
    }
    if (path == '/api/v1/GirlAi/companion/turn') {
      return turnReplyWithMemory();
    }
    if (path == '/api/v1/GirlAi/memories/m1/confirm') {
      expect(method, 'POST');
      return onConfirm == null
          ? throw const SocketException('connection lost')
          : onConfirm();
    }
    if (path == '/api/v1/GirlAi/memories/m1') {
      expect(method, 'DELETE');
      return onDelete == null
          ? throw const SocketException('connection lost')
          : onDelete();
    }
    fail('unexpected $path');
  });

  void useApi(GirlApi next) {
    api = next;
    container.dispose();
    container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
  }

  test('保存记忆网络断开保留候选并显示错误', () async {
    useApi(memoryApi());
    final controller = container.read(girlAiControllerProvider.notifier);
    await controller.send('你好');
    expect(
      container.read(girlAiControllerProvider).memoryCandidates.single.key,
      '喜欢',
    );
    await controller.confirmMemory(
      container.read(girlAiControllerProvider).memoryCandidates.single,
    );
    final state = container.read(girlAiControllerProvider);
    expect(state.error, contains('connection lost'));
    expect(state.memoryCandidates.single.value, '猫');
  });

  test('忽略记忆网络断开保留候选并显示错误', () async {
    useApi(memoryApi());
    final controller = container.read(girlAiControllerProvider.notifier);
    await controller.send('你好');
    await controller.deleteMemory(
      container.read(girlAiControllerProvider).memoryCandidates.single,
    );
    final state = container.read(girlAiControllerProvider);
    expect(state.error, contains('connection lost'));
    expect(state.memoryCandidates.single.id, 'm1');
  });

  testWidgets('保存记忆网络断开显示错误原文并保留卡片', (tester) async {
    useApi(memoryApi());
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
    await tester.pump();
    expect(find.text('喜欢: 猫'), findsOneWidget);
    await tester.tap(find.byTooltip('保存'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('喜欢: 猫'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('忽略记忆网络断开显示错误原文并保留卡片', (tester) async {
    useApi(memoryApi());
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
    await tester.pump();
    await tester.tap(find.byTooltip('忽略'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('喜欢: 猫'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('保存失败后退出再进入会丢掉错误但保留记忆卡片', (tester) async {
    useApi(memoryApi());
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
    await tester.pump();
    await tester.tap(find.byTooltip('保存'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsOneWidget);

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
    expect(find.text('喜欢: 猫'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('保存中退出再进入仍会显示晚到的错误', (tester) async {
    final pending = Completer<Object?>();
    useApi(memoryApi(onConfirm: () => pending.future));
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
    await tester.pump();
    await tester.tap(find.byTooltip('保存'));
    await tester.pump();

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
    expect(find.textContaining('connection lost'), findsNothing);

    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('喜欢: 猫'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
