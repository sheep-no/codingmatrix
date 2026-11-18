import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../auth/authenticated_client.dart';
import '../../domain/models/girl_companion.dart';

class GirlAiClient {
  GirlAiClient(this.api);
  final AuthenticatedClient api;
  Future<Map<String, dynamic>> _map(
    String p, {
    String method = 'GET',
    Object? body,
  }) async => Map<String, dynamic>.from(
    await api.requestJson('/api/v1$p', method: method, body: body) as Map,
  );
  Future<CompanionTurnResponse> turn(
    String prompt,
    String characterId, {
    String? turnId,
  }) async => CompanionTurnResponse.fromJson(
    await _map(
      '/GirlAi/companion/turn',
      method: 'POST',
      body: {
        'prompt': prompt,
        'character_id': characterId,
        if (turnId != null) 'turn_id': turnId,
      },
    ),
  );
  Stream<Map<String, dynamic>> turnStream(
    String prompt,
    String characterId, {
    String? turnId,
  }) => _stream('/GirlAi/companion/turn/stream', {
    'prompt': prompt,
    'character_id': characterId,
    if (turnId != null) 'turn_id': turnId,
  });
  Future<Map<String, dynamic>> state() => _map('/GirlAi/companion/state');
  Future<CompanionTurnResponse> transcribe(
    String text,
    String characterId, {
    String? turnId,
    bool voiceOutput = false,
  }) async => CompanionTurnResponse.fromJson(
    await _map(
      '/GirlAi/voice/transcriptions',
      method: 'POST',
      body: {
        'transcript': text,
        'character_id': characterId,
        if (turnId != null) 'turn_id': turnId,
        'voice_output': voiceOutput,
      },
    ),
  );
  Stream<Map<String, dynamic>> transcribeStream(
    String text,
    String characterId, {
    String? turnId,
    bool voiceOutput = false,
  }) => _stream('/GirlAi/voice/transcriptions/stream', {
    'transcript': text,
    'character_id': characterId,
    if (turnId != null) 'turn_id': turnId,
    'voice_output': voiceOutput,
  });
  Future<List<GirlCharacter>> characters() async => [
    for (final x in (await _map('/GirlAi/characters'))['characters'] as List)
      GirlCharacter.fromJson(Map<String, dynamic>.from(x)),
  ];
  String avatarUrl(String id) =>
      '${api.auth.baseUrl}/api/v1/GirlAi/characters/$id/avatar';
  Future<String> avatarSvg(String id) => api.requestText(avatarUrl(id));
  Future<Map<String, dynamic>> memories({int limit = 20, int offset = 0}) =>
      _map('/GirlAi/memories?limit=$limit&offset=$offset');
  Future<Map<String, dynamic>> confirmMemory(
    String id, {
    String? key,
    String? value,
  }) => _map(
    '/GirlAi/memories/$id/confirm',
    method: 'POST',
    body: {if (key != null) 'key': key, if (value != null) 'value': value},
  );
  Future<Map<String, dynamic>> deleteMemory(String id) =>
      _map('/GirlAi/memories/$id', method: 'DELETE');
  Future<List<GirlHistory>> history() async => [
    for (final x in (await _map('/GirlAi/history'))['records'] as List)
      GirlHistory.fromJson(Map<String, dynamic>.from(x)),
  ];
  Future<List<GirlHistory>> search(String q) async => [
    for (final x
        in (await _map(
              '/GirlAi/history/search?q=${Uri.encodeQueryComponent(q)}',
            ))['records']
            as List)
      GirlHistory.fromJson(Map<String, dynamic>.from(x)),
  ];
  Future<Map<String, dynamic>> deleteHistory({
    List<String> ids = const [],
    bool all = false,
  }) => _map(
    '/GirlAi/history?all=$all${ids.map((x) => '&record_ids=$x').join()}',
    method: 'DELETE',
  );
  Future<List<GirlCharacter>> customCharacters() async => [
    for (final x
        in (await _map('/GirlAi/characters/custom/list'))['characters'] as List)
      GirlCharacter.fromJson(Map<String, dynamic>.from(x)),
  ];
  Future<Map<String, dynamic>> createCharacter(Map<String, dynamic> body) =>
      _map('/GirlAi/characters/custom', method: 'POST', body: body);
  Future<Map<String, dynamic>> deleteCharacter(String id) =>
      _map('/GirlAi/characters/custom/$id', method: 'DELETE');
  Future<Map<String, dynamic>> preferences() => _map('/GirlAi/preferences');
  Future<Map<String, dynamic>> deletePreference(String id) =>
      _map('/GirlAi/preferences/$id', method: 'DELETE');

  Stream<Map<String, dynamic>> _stream(
    String path,
    Map<String, dynamic> body,
  ) async* {
    final request = http.Request(
      'POST',
      Uri.parse(api.auth.baseUrl).resolve('/api/v1$path'),
    );
    request.headers.addAll({
      'Accept': 'text/event-stream',
      'Content-Type': 'application/json',
      'Accept-Encoding': 'identity',
    });
    request.body = jsonEncode(body);
    final response = await api.send(request);
    final contentType = response.headers['content-type'] ?? '';
    // Older backends and test transports answer with a buffered JSON body.
    // Accept both shapes so a deployed mismatch still returns the turn.
    if (!contentType.contains('text/event-stream')) {
      final text = await utf8.decoder.bind(response.stream).join();
      if (text.trim().isEmpty) {
        throw const FormatException('伴侣服务返回了空响应');
      }
      final decoded = jsonDecode(text);
      if (decoded is! Map) {
        throw const FormatException('伴侣服务返回了无效响应');
      }
      yield {'event': 'turn', 'data': Map<String, dynamic>.from(decoded)};
      return;
    }
    yield* _parseSse(response.stream);
  }

  static Stream<Map<String, dynamic>> _parseSse(Stream<List<int>> bytes) {
    var buffer = '';
    return bytes
        .transform(utf8.decoder)
        .transform(
          StreamTransformer<String, Map<String, dynamic>>.fromHandlers(
            handleData: (text, sink) {
              buffer += text;
              var newline = buffer.indexOf('\n');
              while (newline >= 0) {
                final line = buffer.substring(0, newline).trimRight();
                buffer = buffer.substring(newline + 1);
                _addEvent(line, sink);
                newline = buffer.indexOf('\n');
              }
              if (buffer.length > 1024 * 1024) {
                buffer = '';
                sink.addError(const FormatException('伴侣事件过大'));
              }
            },
            handleDone: (sink) {
              _addEvent(buffer.trim(), sink);
              sink.close();
            },
          ),
        );
  }

  static void _addEvent(String line, EventSink<Map<String, dynamic>> sink) {
    if (!line.startsWith('data:')) return;
    final payload = line.substring(5).trim();
    if (payload.isEmpty) return;
    try {
      final decoded = jsonDecode(payload);
      if (decoded is Map) {
        sink.add(Map<String, dynamic>.from(decoded));
      }
    } on FormatException {
      sink.addError(const FormatException('伴侣事件格式异常'));
    }
  }
}
