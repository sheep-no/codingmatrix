import 'dart:async';
import 'dart:convert';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/application/chat_controller.dart';
import 'package:codingmatrix_desktop/infrastructure/chat/chat_client.dart';
import 'package:codingmatrix_desktop/presentation/chat_page.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'agent_delivery_test.dart' show DeliveryApi;

class UploadApi extends DeliveryApi {
  UploadApi() : super((_, _, _) async => null);

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    expect(request.method, 'POST');
    expect(request.url.path, '/api/v1/files/upload');
    final multipart = request as http.MultipartRequest;
    expect(multipart.files.single.field, 'file');
    expect(multipart.files.single.filename, 'pubspec.yaml');
    expect(multipart.files.single.length, greaterThan(0));
    return http.StreamedResponse(
      Stream.value(
        utf8.encode(
          jsonEncode({
            'server_path': 'uploads/pubspec.yaml',
            'name': 'pubspec.yaml',
            'type': 'text/yaml',
          }),
        ),
      ),
      200,
    );
  }
}

class ChatApi extends DeliveryApi {
  ChatApi()
    : super((_, _, _) async => {'response': '同步回复', 'conversation_id': 8});

  final chunks = StreamController<List<int>>();
  final uploadedPaths = <String>[];
  Map<String, dynamic>? body;
  String? endpoint;
  Future<Map<String, dynamic>> Function(String)? upload;

  @override
  Future<Map<String, dynamic>> uploadFile(String path) async {
    uploadedPaths.add(path);
    return upload == null
        ? {
            'server_path': 'uploads/document.txt',
            'name': '服务端文件.txt',
            'type': 'text/plain',
            'ignored': true,
          }
        : await upload!(path);
  }

  @override
  Future<Stream<List<int>>> sendJsonStream(String path, Object request) async {
    endpoint = path;
    body = request as Map<String, dynamic>;
    return chunks.stream;
  }

  @override
  Future<Object?> requestJson(
    String path, {
    String method = 'GET',
    Object? body,
  }) async {
    this.body = body as Map<String, dynamic>;
    return super.requestJson(path, method: method, body: body);
  }
}

class TestPicker extends FilePicker {
  FilePickerResult? result;
  @override
  Future<FilePickerResult?> pickFiles({
    String? dialogTitle,
    String? initialDirectory,
    FileType type = FileType.any,
    List<String>? allowedExtensions,
    Function(FilePickerStatus)? onFileLoading,
    bool allowCompression = true,
    int compressionQuality = 30,
    bool allowMultiple = false,
    bool withData = false,
    bool withReadStream = false,
    bool lockParentWindow = false,
    bool readSequential = false,
  }) async {
    expect(allowMultiple, true);
    return result;
  }
}

Future<void> flush() => Future<void>.delayed(Duration.zero);

void main() {
  test('uploadFile 使用已挂载上传路由和 multipart file 字段', () async {
    final result = await UploadApi().uploadFile('pubspec.yaml');
    expect(result['server_path'], 'uploads/pubspec.yaml');
    expect(result['name'], 'pubspec.yaml');
    expect(result['type'], 'text/yaml');
  });
  test('后端 choices.delta.content 契约及结束后的会话 ID', () async {
    final events = await ChatClient.parseStream(
      Stream.fromIterable([
        utf8.encode('{"choices":[{"delta":{"role":"assistant"}}]}\n'),
        utf8.encode('{"choices":[{"delta":{"content":"回答"}}]}\n'),
        utf8.encode('{"choices":[{"delta":{},"finish_reason":"stop"}]}\n'),
        utf8.encode('{"conversation_id":19}\n'),
      ]),
    ).toList();
    expect(events.map((event) => event.text).join(), '回答');
    expect(events.last.conversationId, 19);
  });

  test('NDJSON 跨 UTF-8 字节分片、CRLF、嵌套 delta 与无尾换行', () async {
    final input =
        '${jsonEncode({'conversation_id': 42})}\r\n'
        '${jsonEncode({
          'delta': {'content': '你好{"x"}'},
        })}\r\n'
        '${jsonEncode({'content': '世界'})}';
    final events = await ChatClient.parseStream(
      Stream.fromIterable(utf8.encode(input).map((byte) => [byte])),
    ).toList();
    expect(events.first.conversationId, 42);
    expect(events.map((event) => event.text).join(), '你好{"x"}世界');
  });

  test('普通文本立即增量输出并保留代码及换行，识别末尾元数据', () async {
    final chunks = StreamController<List<int>>();
    final events = <String>[];
    int? conversationId;
    final subscription = ChatClient.parseStream(chunks.stream).listen((event) {
      events.add(event.text);
      conversationId = event.conversationId ?? conversationId;
    });
    chunks.add(utf8.encode('第一段\n'));
    await flush();
    expect(events.join(), '第一段\n');
    chunks.add(
      utf8.encode('代码 { return 1; }\n{"foo": 2}尾部{"conversation_id": 9}\n'),
    );
    final done = subscription.asFuture<void>();
    await chunks.close();
    await done;
    expect(events.join(), '第一段\n代码 { return 1; }\n{"foo": 2}尾部');
    expect(conversationId, 9);
  });

  test('错误事件保留已收文本并终止后续内容', () async {
    final events = await ChatClient.parseStream(
      Stream.value(
        utf8.encode(
          '{"delta":"部分"}\n{"error":{"message":"额度不足"},"conversation_id":3}\n{"delta":"忽略"}',
        ),
      ),
    ).toList();
    expect(events.map((event) => event.text).join(), '部分');
    expect(events.last.error, '额度不足');
    expect(events.last.conversationId, 3);
  });

  test('字符串流接口保持兼容并将服务错误转成异常', () async {
    final api = ChatApi();
    final result = ChatClient(api).stream(prompt: '你好').toList();
    api.chunks.add(utf8.encode('{"error":"失败"}\n'));
    await expectLater(result, throwsStateError);
    await api.chunks.close();
  });

  late ChatApi api;
  late ProviderContainer container;
  late ChatController controller;
  late TestPicker picker;
  setUp(() {
    picker = TestPicker();
    FilePicker.platform = picker;
    api = ChatApi();
    container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    controller = container.read(chatControllerProvider.notifier);
  });
  tearDown(() {
    container.dispose();
    unawaited(api.chunks.close());
  });

  test('同步调用支持上传附件和既有 files 参数', () async {
    await controller.send(
      '分析',
      filePaths: ['/tmp/a.txt'],
      files: [
        {
          'server_path': 'uploads/old.txt',
          'name': 'old.txt',
          'type': 'text/plain',
        },
      ],
    );
    expect(api.body!['stream'], false);
    expect((api.body!['files'] as List).last, {
      'server_path': 'uploads/document.txt',
      'name': '服务端文件.txt',
      'type': 'text/plain',
    });
    expect((api.body!['files'] as List), hasLength(2));
    expect(container.read(chatControllerProvider).messages.last.text, '同步回复');
  });

  test('流式请求上传映射、增量更新及会话续接', () async {
    final pending = controller.send(
      '分析',
      streaming: true,
      filePaths: ['/tmp/a.txt'],
      model: 'model',
      reasoning: true,
      search: false,
    );
    await flush();
    expect(api.endpoint, '/api/v1/chat');
    expect(api.body!['stream'], true);
    expect(api.body!['model'], 'model');
    expect(api.body!['use_reasoning'], true);
    expect(api.body!['enable_search'], false);
    expect(api.uploadedPaths, ['/tmp/a.txt']);
    expect((api.body!['files'] as List).single, {
      'server_path': 'uploads/document.txt',
      'name': '服务端文件.txt',
      'type': 'text/plain',
    });
    api.chunks.add(utf8.encode('{"conversation_id":42}\n{"delta":"你好"}\n'));
    await flush();
    expect(container.read(chatControllerProvider).messages.last.text, '你好');
    expect(container.read(chatControllerProvider).loading, true);
    await api.chunks.close();
    await pending;
    await controller.send('继续');
    expect(api.body!['conversation_id'], 42);
  });

  test('上传失败或缺少路径时停止发送并退出忙碌状态', () async {
    api.upload = (_) async => {'name': 'a.txt'};
    await controller.send('分析', streaming: true, filePaths: ['/tmp/a.txt']);
    expect(api.body, isNull);
    expect(
      container.read(chatControllerProvider).error,
      contains('server_path'),
    );
    expect(container.read(chatControllerProvider).loading, false);
    expect(container.read(chatControllerProvider).uploading, false);
    api.upload = (_) async => throw StateError('上传失败');
    await controller.send('分析', filePaths: ['/tmp/a.txt']);
    expect(container.read(chatControllerProvider).error, contains('上传失败'));
  });

  test('取消流会取消订阅并保留部分内容', () async {
    var cancelled = false;
    api.chunks.onCancel = () => cancelled = true;
    final pending = controller.send('问题', streaming: true);
    await flush();
    api.chunks.add(utf8.encode('部分内容'));
    await flush();
    controller.cancel();
    await pending;
    await flush();
    expect(cancelled, true);
    expect(container.read(chatControllerProvider).cancelled, true);
    expect(container.read(chatControllerProvider).loading, false);
    expect(container.read(chatControllerProvider).messages.last.text, '部分内容');
    controller.reset();
    api.chunks.add(utf8.encode('旧响应'));
    await flush();
    expect(container.read(chatControllerProvider).messages, isEmpty);
  });

  test('上传期间取消及重置后忽略晚到的上传结果', () async {
    final upload = Completer<Map<String, dynamic>>();
    api.upload = (_) => upload.future;
    final pending = controller.send(
      '问题',
      streaming: true,
      filePaths: ['/tmp/a.txt'],
    );
    expect(container.read(chatControllerProvider).uploading, true);
    controller.cancel();
    await pending;
    controller.reset();
    upload.complete({'server_path': 'uploads/a.txt'});
    await pending;
    expect(api.body, isNull);
    expect(container.read(chatControllerProvider).messages, isEmpty);
  });

  test('流断线保留部分内容并显示错误', () async {
    final pending = controller.send('问题', streaming: true);
    await flush();
    api.chunks.add(utf8.encode('部分内容'));
    api.chunks.addError(StateError('连接中断'));
    await pending;
    final state = container.read(chatControllerProvider);
    expect(state.error, contains('连接中断'));
    expect(state.messages.last.text, '部分内容');
    expect(state.loading, false);
  });

  testWidgets('选择多个附件、去重、移除、上传并展示流式内容及取消', (tester) async {
    picker.result = FilePickerResult([
      PlatformFile(name: 'a.txt', path: '/tmp/a.txt', size: 10),
      PlatformFile(name: 'b.txt', path: '/tmp/b.txt', size: 20),
    ]);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ChatPage()),
      ),
    );
    await tester.tap(find.byKey(const Key('chatAttachButton')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('chatAttachButton')));
    await tester.pumpAndSettle();
    expect(find.byType(InputChip), findsNWidgets(2));
    final chip = find.widgetWithText(InputChip, 'b.txt');
    await tester.tap(
      find.descendant(of: chip, matching: find.byType(Icon)).last,
    );
    await tester.pumpAndSettle();
    expect(find.text('b.txt'), findsNothing);
    await tester.enterText(find.byKey(const Key('chatPromptField')), '分析附件');
    await tester.tap(find.byKey(const Key('chatSendButton')));
    await tester.pumpAndSettle();
    expect(api.uploadedPaths, ['/tmp/a.txt']);
    api.chunks.add(utf8.encode('回答'));
    await tester.pumpAndSettle();
    expect(find.text('回答'), findsOneWidget);
    await tester.tap(find.byKey(const Key('chatSendButton')));
    await tester.pumpAndSettle();
    expect(find.text('已取消，已接收的内容已保留'), findsOneWidget);
    expect(find.text('a.txt'), findsOneWidget);
  });

  testWidgets('上传错误保留输入和附件，空白消息不会上传', (tester) async {
    picker.result = FilePickerResult([
      PlatformFile(name: 'a.txt', path: '/tmp/a.txt', size: 10),
    ]);
    api.upload = (_) async => throw StateError('上传失败');
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ChatPage()),
      ),
    );
    await tester.tap(find.byKey(const Key('chatAttachButton')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('chatSendButton')));
    await tester.pumpAndSettle();
    expect(api.uploadedPaths, isEmpty);
    await tester.enterText(find.byKey(const Key('chatPromptField')), '分析');
    await tester.tap(find.byKey(const Key('chatSendButton')));
    await tester.pumpAndSettle();
    expect(find.textContaining('上传失败'), findsOneWidget);
    expect(find.text('a.txt'), findsOneWidget);
    expect(
      tester
          .widget<TextField>(find.byKey(const Key('chatPromptField')))
          .controller!
          .text,
      '分析',
    );
  });
}
