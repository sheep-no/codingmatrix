import 'dart:async';

import '../auth/authenticated_client.dart';
import '../../domain/models/chat_models.dart';
import 'dart:convert';

class ChatClient {
  ChatClient(this.api);

  final AuthenticatedClient api;

  Future<ChatReply> send({
    required String prompt,
    int? conversationId,
    String? model,
    bool reasoning = false,
    bool? search,
    List<Map<String, dynamic>>? files,
  }) async {
    final result = await api.requestJson(
      '/api/v1/chat',
      method: 'POST',
      body: {
        'prompt': prompt,
        'stream': false,
        if (conversationId != null) 'conversation_id': conversationId,
        if (model != null) 'model': model,
        'use_reasoning': reasoning,
        if (search != null) 'enable_search': search,
        if (files != null) 'files': files,
      },
    );
    return ChatReply.fromJson(Map<String, dynamic>.from(result as Map));
  }

  Stream<String> stream({
    required String prompt,
    int? conversationId,
    String? model,
    bool reasoning = false,
    bool? search,
    List<Map<String, dynamic>>? files,
  }) async* {
    await for (final event in streamEvents(
      prompt: prompt,
      conversationId: conversationId,
      model: model,
      reasoning: reasoning,
      search: search,
      files: files,
    )) {
      if (event.error != null) throw StateError(event.error!);
      if (event.text.isNotEmpty) yield event.text;
    }
  }

  Stream<ChatStreamEvent> streamEvents({
    required String prompt,
    int? conversationId,
    String? model,
    bool reasoning = false,
    bool? search,
    List<Map<String, dynamic>>? files,
  }) async* {
    final request = await api.sendJsonStream('/api/v1/chat', {
      'prompt': prompt,
      'stream': true,
      if (conversationId != null) 'conversation_id': conversationId,
      if (model != null) 'model': model,
      'use_reasoning': reasoning,
      if (search != null) 'enable_search': search,
      if (files != null) 'files': files,
    });
    yield* parseStream(request);
  }

  // The server can append JSON metadata directly after unframed plain text.
  static Stream<ChatStreamEvent> parseStream(Stream<List<int>> bytes) {
    var buffer = '';
    var skipNewline = false;
    // A transformer forwards cancellation even while the source is idle.
    return bytes
        .transform(utf8.decoder)
        .transform(
          StreamTransformer<String, ChatStreamEvent>.fromHandlers(
            handleData: (chunk, sink) {
              buffer += chunk;
              while (buffer.isNotEmpty) {
                if (skipNewline) {
                  if (buffer == '\r') break;
                  if (buffer.startsWith('\r\n')) {
                    buffer = buffer.substring(2);
                  } else if (buffer.startsWith('\n')) {
                    buffer = buffer.substring(1);
                  }
                  skipNewline = false;
                  if (buffer.isEmpty) break;
                }
                final start = buffer.indexOf('{');
                if (start != 0) {
                  final end = start < 0 ? buffer.length : start;
                  sink.add(ChatStreamEvent(text: buffer.substring(0, end)));
                  buffer = buffer.substring(end);
                  continue;
                }
                var depth = 0;
                var quoted = false;
                var escaped = false;
                var end = -1;
                for (var i = 0; i < buffer.length; i++) {
                  final char = buffer[i];
                  if (quoted) {
                    if (escaped) {
                      escaped = false;
                    } else if (char == '\\') {
                      escaped = true;
                    } else if (char == '"') {
                      quoted = false;
                    }
                  } else if (char == '"') {
                    quoted = true;
                  } else if (char == '{') {
                    depth++;
                  } else if (char == '}' && --depth == 0) {
                    end = i + 1;
                    break;
                  }
                }
                if (end < 0) break;
                final raw = buffer.substring(0, end);
                buffer = buffer.substring(end);
                Map<String, dynamic>? json;
                try {
                  json = jsonDecode(raw) as Map<String, dynamic>;
                } on FormatException {
                  // Braces in prose/code are preserved verbatim.
                }
                if (json == null ||
                    !json.keys.any(
                      (key) => const {
                        'conversation_id',
                        'delta',
                        'content',
                        'response',
                        'error',
                        'done',
                        'interrupted',
                        'choices',
                      }.contains(key),
                    )) {
                  sink.add(ChatStreamEvent(text: raw));
                  continue;
                }
                skipNewline = true;
                final id = int.tryParse('${json['conversation_id']}');
                final error = json['error'];
                final choices = json['choices'];
                final choice =
                    choices is List &&
                        choices.isNotEmpty &&
                        choices.first is Map
                    ? choices.first as Map
                    : const {};
                final delta =
                    json['delta'] ??
                    json['content'] ??
                    json['response'] ??
                    choice['delta'];
                sink.add(
                  ChatStreamEvent(
                    conversationId: id,
                    text: delta is Map
                        ? (delta['content'] ?? '').toString()
                        : (delta ?? '').toString(),
                    error: error != null
                        ? (error is Map
                                  ? error['message'] ?? error['detail'] ?? error
                                  : error)
                              .toString()
                        : json['interrupted'] == true
                        ? '响应已中断，请确认会话状态后重试'
                        : null,
                  ),
                );
                if (error != null ||
                    json['interrupted'] == true ||
                    json['done'] == true) {
                  sink.close();
                  return;
                }
              }
            },
            handleDone: (sink) {
              if (buffer.isNotEmpty) sink.add(ChatStreamEvent(text: buffer));
              sink.close();
            },
          ),
        );
  }

  Future<List<ChatHistoryItem>> history({int limit = 20}) async {
    final result =
        await api.requestJson(
              '/api/v1/history',
              method: 'POST',
              body: {'limit': limit, 'offset': 0},
            )
            as Map;
    return (result['items'] as List)
        .map(
          (item) =>
              ChatHistoryItem.fromJson(Map<String, dynamic>.from(item as Map)),
        )
        .toList();
  }

  Future<List<ChatMessage>> detail(int conversationId) async {
    final result =
        await api.requestJson(
              '/api/v1/conversation/history',
              method: 'POST',
              body: {'conversation_id': conversationId, 'limit': 50},
            )
            as Map;
    return (result['items'] as List).map((item) {
      final json = Map<String, dynamic>.from(item as Map);
      return ChatMessage(
        text: (json['prompt'] ?? json['content'] ?? '').toString(),
        fromUser: (json['role'] ?? 'user') == 'user',
      );
    }).toList();
  }
}
