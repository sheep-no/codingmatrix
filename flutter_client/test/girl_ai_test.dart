import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/application/girl_ai_controller.dart';
import 'package:codingmatrix_desktop/domain/models/girl_companion.dart';
import 'package:codingmatrix_desktop/infrastructure/girl/girl_ai_client.dart';
import 'package:codingmatrix_desktop/presentation/virtual_girl_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'agent_delivery_test.dart' show DeliveryApi;
import 'auth_session_test.dart' show Fixture;
import 'module_lifecycle_test.dart' show ModuleAuth;

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

  testWidgets('窄屏下情绪意图与语音标签同时出现不溢出', (tester) async {
    tester.view.physicalSize = const Size(360, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    api = GirlApi((path, method, body) async {
      if (path == '/api/v1/GirlAi/characters') {
        return {
          'characters': [
            {'id': 'gentle', 'name': '温柔'},
          ],
        };
      }
      if (path == '/api/v1/GirlAi/companion/turn') {
        return {
          'assistant_text': '嗨',
          'turn_id': 't1',
          'emotion': {'label': 'stressed'},
          'intent': {'label': 'task_execution'},
          'voice_input': {'status': 'received'},
        };
      }
      fail('unexpected $path');
    });
    container.dispose();
    container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    await container.read(girlAiControllerProvider.notifier).send('你好');

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: VirtualGirlPage()),
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(find.text('情绪: stressed'), findsOneWidget);
    expect(find.text('意图: task_execution'), findsOneWidget);
    expect(find.text('语音已识别'), findsOneWidget);
    expect(tester.takeException(), isNull);
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

  testWidgets('切换账号清空未发送的输入草稿', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final local = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        authenticatedClientProvider.overrideWithValue(api),
      ],
    );
    addTearDown(local.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: local,
        child: const MaterialApp(home: VirtualGirlPage()),
      ),
    );
    await tester.pump();
    await tester.pump();

    await tester.enterText(find.byType(TextField), '上一账号的草稿');
    expect(find.text('上一账号的草稿'), findsOneWidget);

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    expect(find.text('上一账号的草稿'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('切换账号后重新加载角色列表', (tester) async {
    var calls = 0;
    api = GirlApi((path, _, __) async {
      if (path == '/api/v1/GirlAi/characters') {
        calls++;
        return {
          'characters': [
            {'id': 'gentle', 'name': '温柔'},
          ],
        };
      }
      fail('unexpected $path');
    });
    container.dispose();
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        authenticatedClientProvider.overrideWithValue(api),
      ],
    );

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: VirtualGirlPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(calls, 1);
    expect(find.text('温柔'), findsOneWidget);

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    // The account-scoped controller drops its state, so the role list has to
    // be fetched again for the next account.
    expect(calls, 2);
    expect(find.text('温柔'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test('切账号后历史读取仍会写入新账号', () async {
    var calls = 0;
    api = GirlApi((path, _, __) async {
      if (path == '/api/v1/GirlAi/history') {
        calls++;
        return {
          'records': [
            {'id': 'h$calls', 'role': 'user', 'content': '记录$calls'},
          ],
        };
      }
      fail('unexpected $path');
    });
    container.dispose();
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        authenticatedClientProvider.overrideWithValue(api),
      ],
    );

    await container.read(girlAiControllerProvider.notifier).loadHistory();
    expect(
      container.read(girlAiControllerProvider).history.single.content,
      '记录1',
    );

    auth.switchAccount('bob');
    await container.read(girlAiControllerProvider.notifier).loadHistory();
    expect(
      container.read(girlAiControllerProvider).history.single.content,
      '记录2',
    );
  });

  test('切账号后晚到的虚拟姬回复不会写入新账号', () async {
    final fixture = Fixture();
    final gate = Completer<http.Response>();
    fixture.business = (request) async {
      if (request.url.path == '/api/v1/GirlAi/companion/turn') {
        return gate.future;
      }
      return http.Response('{}', 200);
    };
    container.dispose();
    container = ProviderContainer(
      overrides: [
        credentialStoreProvider.overrideWithValue(fixture.store),
        httpClientProvider.overrideWithValue(fixture.transport),
        cloudAuthClientProvider.overrideWithValue(fixture.auth),
      ],
    );
    final auth = container.read(authControllerProvider.notifier);
    await Future<void>.delayed(Duration.zero);
    await auth.login(email: 'alice@example.com', password: 'test-password');
    final pending = container
        .read(girlAiControllerProvider.notifier)
        .send('你好');
    await Future<void>.delayed(Duration.zero);
    expect(container.read(girlAiControllerProvider).loading, true);
    await auth.logout();
    gate.complete(
      http.Response.bytes(
        utf8.encode(jsonEncode(turnReply(text: '旧账号回复'))),
        200,
      ),
    );
    await pending;
    final state = container.read(girlAiControllerProvider);
    expect(state.messages, isEmpty);
    expect(state.error, isNull);
    expect(state.loading, false);
  });

  test('切账号后晚到的记忆确认不会抛出未处理异常', () async {
    final fixture = Fixture();
    final gate = Completer<http.Response>();
    fixture.business = (request) async {
      if (request.url.path == '/api/v1/GirlAi/memories/m1/confirm') {
        return gate.future;
      }
      return http.Response('{}', 200);
    };
    container.dispose();
    container = ProviderContainer(
      overrides: [
        credentialStoreProvider.overrideWithValue(fixture.store),
        httpClientProvider.overrideWithValue(fixture.transport),
        cloudAuthClientProvider.overrideWithValue(fixture.auth),
      ],
    );
    final auth = container.read(authControllerProvider.notifier);
    await Future<void>.delayed(Duration.zero);
    await auth.login(email: 'alice@example.com', password: 'test-password');
    container.read(girlAiControllerProvider);
    final pending = container
        .read(girlAiControllerProvider.notifier)
        .confirmMemory(const MemoryCandidate(id: 'm1', key: '喜欢', value: '猫'));
    await Future<void>.delayed(Duration.zero);
    await auth.logout();
    // Reading the state rebuilds the notifier, which is what a mounted page
    // does once the account changes.
    container.read(girlAiControllerProvider);
    gate.complete(http.Response.bytes(utf8.encode('{}'), 200));
    await pending;
    final state = container.read(girlAiControllerProvider);
    expect(state.memoryCandidates, isEmpty);
    expect(state.error, isNull);
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

  testWidgets('生成回复中按回车不会丢掉还没发送的草稿', (tester) async {
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
    await tester.enterText(find.byType(TextField), '第一条');
    await tester.tap(find.byIcon(Icons.send));
    await tester.pump();
    expect(container.read(girlAiControllerProvider).loading, true);

    // The send button is disabled while a reply streams, but the field is
    // still editable: pressing enter must keep the draft instead of dropping
    // a message the controller refuses to send.
    await tester.enterText(find.byType(TextField), '第二条');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();
    expect(find.text('第二条'), findsOneWidget);
    expect(find.text('第一条'), findsOneWidget);

    pending.complete(turnReply(text: '嗨'));
    await tester.pump();
    await tester.pump();
    expect(find.text('嗨'), findsOneWidget);
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

  testWidgets('打开历史进行中无法再次触发并发请求', (tester) async {
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
    await tester.tap(find.byTooltip('历史记录'));
    await tester.pump();
    expect(historyCalls, 1);
    await tester.tap(find.byTooltip('历史记录'), warnIfMissed: false);
    await tester.pump();
    expect(historyCalls, 1);
    pending.complete({'records': []});
    await tester.pump();
    await tester.pump();
    expect(find.text('暂无历史记录'), findsOneWidget);
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

  testWidgets('切账号关闭已打开的历史弹层', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final scoped = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        authenticatedClientProvider.overrideWithValue(
          GirlApi((path, _, __) async {
            if (path == '/api/v1/GirlAi/characters') return {'characters': []};
            if (path == '/api/v1/GirlAi/history') {
              return {
                'records': [
                  {'id': 'h1', 'role': 'user', 'content': '上一账号的历史'},
                ],
              };
            }
            fail('unexpected $path');
          }),
        ),
      ],
    );
    addTearDown(scoped.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: scoped,
        child: const MaterialApp(home: VirtualGirlPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byTooltip('历史记录'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('上一账号的历史'), findsOneWidget);

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    expect(find.text('上一账号的历史'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('切账号后旧账号的历史弹层不会弹出', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final pending = Completer<Object?>();
    var historyCalls = 0;
    final scoped = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        authenticatedClientProvider.overrideWithValue(
          GirlApi((path, _, __) async {
            if (path == '/api/v1/GirlAi/characters') {
              return {'characters': []};
            }
            if (path == '/api/v1/GirlAi/history') {
              historyCalls++;
              if (historyCalls == 1) return pending.future;
              return {'records': []};
            }
            fail('unexpected $path');
          }),
        ),
      ],
    );
    addTearDown(scoped.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: scoped,
        child: const MaterialApp(home: VirtualGirlPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byTooltip('历史记录'));
    await tester.pump();

    auth.switchAccount('bob');
    await tester.pump();
    await tester.pump();

    pending.complete({
      'records': [
        {'id': 'h1', 'role': 'user', 'content': '上一账号的历史'},
      ],
    });
    await tester.pumpAndSettle();

    expect(find.text('上一账号的历史'), findsNothing);
    expect(find.text('暂无历史记录'), findsNothing);
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
        child: MaterialApp(key: UniqueKey(), home: const VirtualGirlPage()),
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

  testWidgets('保存记忆进行中无法再次触发并发请求', (tester) async {
    var confirms = 0;
    final pending = Completer<Object?>();
    useApi(
      memoryApi(
        onConfirm: () {
          confirms++;
          return pending.future;
        },
      ),
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
    expect(find.text('喜欢: 猫'), findsOneWidget);
    await tester.tap(find.byTooltip('保存'));
    await tester.pump();
    expect(confirms, 1);
    await tester.tap(find.byTooltip('保存'), warnIfMissed: false);
    await tester.pump();
    expect(confirms, 1);
    pending.complete(null);
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('忽略记忆进行中无法再次触发并发请求', (tester) async {
    var deletes = 0;
    final pending = Completer<Object?>();
    useApi(
      memoryApi(
        onDelete: () {
          deletes++;
          return pending.future;
        },
      ),
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
    expect(find.text('喜欢: 猫'), findsOneWidget);
    await tester.tap(find.byTooltip('忽略'));
    await tester.pump();
    expect(deletes, 1);
    await tester.tap(find.byTooltip('忽略'), warnIfMissed: false);
    await tester.pump();
    expect(deletes, 1);
    pending.complete(null);
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull);
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

  test('头像地址指向角色头像端点', () {
    expect(
      GirlAiClient(api).avatarUrl('gentle'),
      'https://example.com/api/v1/GirlAi/characters/gentle/avatar',
    );
  });

  test('语音发送走后端转写接口并记录语音状态', () async {
    final bodies = <Object?>[];
    useApi(
      GirlApi((path, method, body) async {
        if (path == '/api/v1/GirlAi/characters') {
          return {
            'characters': [
              {'id': 'gentle', 'name': '温柔'},
            ],
          };
        }
        if (path == '/api/v1/GirlAi/voice/transcriptions') {
          expect(method, 'POST');
          bodies.add(body);
          return {
            ...turnReply(text: '在呢'),
            'voice_input': {'status': 'received'},
          };
        }
        fail('unexpected $path');
      }),
    );
    await container.read(girlAiControllerProvider.notifier).sendVoice('你好');
    final state = container.read(girlAiControllerProvider);
    expect(bodies.single, {
      'transcript': '你好',
      'character_id': 'gentle',
      'voice_output': false,
    });
    expect(state.messages.map((message) => message.content), ['你好', '在呢']);
    expect(state.voiceInput?.status, 'received');
  });

  testWidgets('打开语音模式后发送走转写接口', (tester) async {
    var transcribed = 0;
    useApi(
      GirlApi((path, method, body) async {
        if (path == '/api/v1/GirlAi/characters') {
          return {
            'characters': [
              {'id': 'gentle', 'name': '温柔'},
            ],
          };
        }
        if (path == '/api/v1/GirlAi/voice/transcriptions') {
          transcribed++;
          return {
            ...turnReply(text: '在呢'),
            'voice_input': {'status': 'received'},
          };
        }
        fail('unexpected $path');
      }),
    );
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: VirtualGirlPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byTooltip('语音输入'));
    await tester.pump();
    expect(find.text('语音模式：发送将按语音转写处理'), findsOneWidget);
    await tester.enterText(find.byType(TextField), '你好');
    await tester.tap(find.byIcon(Icons.send));
    await tester.pump();
    await tester.pump();
    expect(transcribed, 1);
    expect(find.text('在呢'), findsOneWidget);
    expect(find.text('语音已识别'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test('搜索历史使用 search 端点', () async {
    String? requested;
    useApi(
      GirlApi((path, method, body) async {
        if (path.startsWith('/api/v1/GirlAi/history/search')) {
          requested = path;
          return {
            'records': [
              {'id': 'h2', 'role': 'assistant', 'content': '猫'},
            ],
          };
        }
        fail('unexpected $path');
      }),
    );
    await container
        .read(girlAiControllerProvider.notifier)
        .loadHistory(query: '猫');
    expect(
      requested,
      '/api/v1/GirlAi/history/search?q=${Uri.encodeQueryComponent('猫')}',
    );
    expect(
      container.read(girlAiControllerProvider).history.single.content,
      '猫',
    );
  });

  test('删除全部历史调用接口并清空列表', () async {
    final calls = <String>[];
    useApi(
      GirlApi((path, method, body) async {
        if (path == '/api/v1/GirlAi/history' && method == 'GET') {
          return {
            'records': [
              {'id': 'h1', 'role': 'user', 'content': '记录'},
            ],
          };
        }
        if (path == '/api/v1/GirlAi/history?all=true' && method == 'DELETE') {
          calls.add(path);
          return {'status': 'deleted', 'count': 1};
        }
        fail('unexpected $path');
      }),
    );
    final controller = container.read(girlAiControllerProvider.notifier);
    await controller.loadHistory();
    expect(container.read(girlAiControllerProvider).history, isNotEmpty);
    await controller.deleteHistoryRecords(all: true);
    expect(calls.single, '/api/v1/GirlAi/history?all=true');
    expect(container.read(girlAiControllerProvider).history, isEmpty);
  });

  test('删除单条历史只移除命中的记录', () async {
    final calls = <String>[];
    useApi(
      GirlApi((path, method, body) async {
        if (path == '/api/v1/GirlAi/history' && method == 'GET') {
          return {
            'records': [
              {'id': 'h1', 'role': 'user', 'content': '一'},
              {'id': 'h2', 'role': 'assistant', 'content': '二'},
            ],
          };
        }
        if (path == '/api/v1/GirlAi/history?all=false&record_ids=h1' &&
            method == 'DELETE') {
          calls.add(path);
          return {'status': 'deleted', 'count': 1};
        }
        fail('unexpected $path');
      }),
    );
    final controller = container.read(girlAiControllerProvider.notifier);
    await controller.loadHistory();
    await controller.deleteHistoryRecords(ids: ['h1']);
    expect(calls.single, '/api/v1/GirlAi/history?all=false&record_ids=h1');
    expect(
      container.read(girlAiControllerProvider).history.single.content,
      '二',
    );
  });

  test('加载并删除已保存记忆', () async {
    final deleted = <String>[];
    useApi(
      GirlApi((path, method, body) async {
        if (path.startsWith('/api/v1/GirlAi/memories?')) {
          return {
            'memories': [
              {
                'id': 'm9',
                'key': '城市',
                'value': '上海',
                'confidence': 80,
                'status': 'confirmed',
              },
            ],
            'total': 1,
            'limit': 20,
            'offset': 0,
          };
        }
        if (path == '/api/v1/GirlAi/memories/m9' && method == 'DELETE') {
          deleted.add(path);
          return {'status': 'deleted', 'id': 'm9'};
        }
        fail('unexpected $path');
      }),
    );
    final controller = container.read(girlAiControllerProvider.notifier);
    await controller.loadMemories();
    expect(container.read(girlAiControllerProvider).memories.single.key, '城市');
    await controller.removeMemory('m9');
    expect(deleted.single, '/api/v1/GirlAi/memories/m9');
    expect(container.read(girlAiControllerProvider).memories, isEmpty);
  });

  test('加载并删除偏好', () async {
    final deleted = <String>[];
    useApi(
      GirlApi((path, method, body) async {
        if (path == '/api/v1/GirlAi/preferences') {
          return {
            'preferences': [
              {'id': 'p1', 'key': '语气', 'value': '轻松'},
            ],
          };
        }
        if (path == '/api/v1/GirlAi/preferences/p1' && method == 'DELETE') {
          deleted.add(path);
          return {'status': 'deleted', 'id': 'p1'};
        }
        fail('unexpected $path');
      }),
    );
    final controller = container.read(girlAiControllerProvider.notifier);
    await controller.loadPreferences();
    expect(
      container.read(girlAiControllerProvider).preferences.single.key,
      '语气',
    );
    await controller.removePreference('p1');
    expect(deleted.single, '/api/v1/GirlAi/preferences/p1');
    expect(container.read(girlAiControllerProvider).preferences, isEmpty);
  });

  test('自定义角色加载加前缀且删除时去掉前缀', () async {
    final deleted = <String>[];
    useApi(
      GirlApi((path, method, body) async {
        if (path == '/api/v1/GirlAi/characters/custom/list') {
          return {
            'characters': [
              {
                'id': 'u1',
                'name': '小助手',
                'description': '自定义',
                'tags': ['a'],
                'avatar_color': '#667eea',
              },
            ],
          };
        }
        if (path == '/api/v1/GirlAi/characters/custom/u1' &&
            method == 'DELETE') {
          deleted.add(path);
          return {'status': 'deleted', 'id': 'u1'};
        }
        fail('unexpected $path');
      }),
    );
    final controller = container.read(girlAiControllerProvider.notifier);
    await controller.loadCustomCharacters();
    final custom = container
        .read(girlAiControllerProvider)
        .customCharacters
        .single;
    expect(custom.id, 'custom_u1');
    expect(custom.avatarColor, '#667eea');
    await controller.deleteCharacter('custom_u1');
    expect(deleted.single, '/api/v1/GirlAi/characters/custom/u1');
    expect(container.read(girlAiControllerProvider).customCharacters, isEmpty);
  });

  test('创建角色提交字段并刷新自定义角色列表', () async {
    Object? posted;
    var listCalls = 0;
    useApi(
      GirlApi((path, method, body) async {
        if (path == '/api/v1/GirlAi/characters/custom' && method == 'POST') {
          posted = body;
          return {'id': 'u2', 'name': '新角色'};
        }
        if (path == '/api/v1/GirlAi/characters/custom/list') {
          listCalls++;
          return {
            'characters': [
              {
                'id': 'u2',
                'name': '新角色',
                'description': '',
                'tags': [],
                'avatar_color': '#ffffff',
              },
            ],
          };
        }
        fail('unexpected $path');
      }),
    );
    final ok = await container
        .read(girlAiControllerProvider.notifier)
        .createCharacter({'name': '新角色', 'speaking_style': '简洁'});
    expect(ok, true);
    expect(posted, {'name': '新角色', 'speaking_style': '简洁'});
    expect(listCalls, 1);
    expect(
      container.read(girlAiControllerProvider).customCharacters.single.name,
      '新角色',
    );
  });

  testWidgets('打开记忆库显示已保存记忆和偏好', (tester) async {
    useApi(
      GirlApi((path, method, body) async {
        if (path == '/api/v1/GirlAi/characters') return {'characters': []};
        if (path.startsWith('/api/v1/GirlAi/memories?')) {
          return {
            'memories': [
              {
                'id': 'm9',
                'key': '城市',
                'value': '上海',
                'confidence': 80,
                'status': 'confirmed',
              },
            ],
            'total': 1,
            'limit': 20,
            'offset': 0,
          };
        }
        if (path == '/api/v1/GirlAi/preferences') {
          return {
            'preferences': [
              {'id': 'p1', 'key': '语气', 'value': '轻松'},
            ],
          };
        }
        fail('unexpected $path');
      }),
    );
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: VirtualGirlPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byTooltip('记忆库'));
    await tester.pumpAndSettle();
    expect(find.text('城市: 上海'), findsOneWidget);
    expect(find.text('语气: 轻松'), findsOneWidget);
    expect(find.text('暂无已保存记忆'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('打开角色库显示自定义角色并可选用', (tester) async {
    useApi(
      GirlApi((path, method, body) async {
        if (path == '/api/v1/GirlAi/characters') {
          return {
            'characters': [
              {'id': 'gentle', 'name': '温柔'},
            ],
          };
        }
        if (path == '/api/v1/GirlAi/characters/custom/list') {
          return {
            'characters': [
              {
                'id': 'u1',
                'name': '小助手',
                'description': '自定义',
                'tags': [],
                'avatar_color': '#667eea',
              },
            ],
          };
        }
        if (path.endsWith('/api/v1/GirlAi/characters/gentle/avatar')) {
          return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">'
              '<rect width="1" height="1" fill="#667eea"/></svg>';
        }
        fail('unexpected $path');
      }),
    );
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: VirtualGirlPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byTooltip('角色库'));
    await tester.pumpAndSettle();
    expect(find.text('小助手'), findsOneWidget);
    await tester.tap(find.text('使用').last);
    await tester.pumpAndSettle();
    expect(container.read(girlAiControllerProvider).character, 'custom_u1');
    expect(tester.takeException(), isNull);
  });

  test('切账号后晚到的记忆库写入不会落到新账号', () async {
    final fixture = Fixture();
    final gate = Completer<http.Response>();
    fixture.business = (request) async {
      if (request.url.path == '/api/v1/GirlAi/memories') {
        return gate.future;
      }
      return http.Response('{}', 200);
    };
    container.dispose();
    container = ProviderContainer(
      overrides: [
        credentialStoreProvider.overrideWithValue(fixture.store),
        httpClientProvider.overrideWithValue(fixture.transport),
        cloudAuthClientProvider.overrideWithValue(fixture.auth),
      ],
    );
    final auth = container.read(authControllerProvider.notifier);
    await Future<void>.delayed(Duration.zero);
    await auth.login(email: 'alice@example.com', password: 'test-password');
    final pending = container
        .read(girlAiControllerProvider.notifier)
        .loadMemories();
    await Future<void>.delayed(Duration.zero);
    await auth.logout();
    container.read(girlAiControllerProvider);
    gate.complete(
      http.Response.bytes(
        utf8.encode(
          jsonEncode({
            'memories': [
              {'id': 'm9', 'key': '城市', 'value': '上海', 'status': 'confirmed'},
            ],
          }),
        ),
        200,
      ),
    );
    await pending;
    expect(container.read(girlAiControllerProvider).memories, isEmpty);
  });
}
