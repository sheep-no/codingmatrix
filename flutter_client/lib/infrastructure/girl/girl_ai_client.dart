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
  Future<Map<String, dynamic>> state() => _map('/GirlAi/companion/state');
  Future<Map<String, dynamic>> transcribe(String text, String characterId) =>
      _map(
        '/GirlAi/voice/transcriptions',
        method: 'POST',
        body: {'transcript': text, 'character_id': characterId},
      );
  Future<List<GirlCharacter>> characters() async => [
    for (final x in (await _map('/GirlAi/characters'))['characters'] as List)
      GirlCharacter.fromJson(Map<String, dynamic>.from(x)),
  ];
  Future<String> avatarUrl(String id) async =>
      '${api.auth.baseUrl}/api/v1/GirlAi/characters/$id/avatar';
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
}
