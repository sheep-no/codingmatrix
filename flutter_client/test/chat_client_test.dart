import 'package:flutter_test/flutter_test.dart';
import 'package:codingmatrix_desktop/infrastructure/chat/chat_client.dart';
import 'agent_delivery_test.dart' show DeliveryApi;

void main() {
  test('同步聊天发送网页端契约并续接 conversation_id', () async {
    final requests = <Object?>[];
    final client = ChatClient(
      DeliveryApi((path, method, body) async {
        expect(path, '/api/v1/chat');
        expect(method, 'POST');
        requests.add(body);
        return {'response': '你好，我是助手。', 'conversation_id': 42};
      }),
    );

    final first = await client.send(prompt: '你好');
    final second = await client.send(
      prompt: '继续',
      conversationId: first.conversationId,
    );

    expect(first.text, '你好，我是助手。');
    expect(first.conversationId, 42);
    expect((requests[0] as Map)['stream'], false);
    expect((requests[1] as Map)['conversation_id'], 42);
    expect(second.conversationId, 42);
  });

  test('聊天历史读取网页端 items 契约', () async {
    final client = ChatClient(
      DeliveryApi((path, method, body) async {
        expect(path, '/api/v1/history');
        expect(method, 'POST');
        expect((body as Map)['offset'], 0);
        return {
          'items': [
            {'conversation_id': 7, 'prompt': '第一次提问'},
          ],
        };
      }),
    );

    final items = await client.history();
    expect(items.single.id, 7);
    expect(items.single.title, '第一次提问');
  });

  test('聊天详情发送 conversation_id 并解析消息', () async {
    final client = ChatClient(
      DeliveryApi((path, method, body) async {
        expect(path, '/api/v1/conversation/history');
        expect((body as Map)['conversation_id'], 7);
        return {
          'conversation_id': 7,
          'items': [
            {'role': 'user', 'content': '你好'},
            {'role': 'assistant', 'content': '你好！'},
          ],
        };
      }),
    );
    final messages = await client.detail(7);
    expect(messages.map((message) => message.text), ['你好', '你好！']);
    expect(messages.first.fromUser, true);
    expect(messages.last.fromUser, false);
  });
}
