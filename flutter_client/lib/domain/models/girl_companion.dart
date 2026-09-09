class EmotionState {
  const EmotionState({
    this.label = 'neutral',
    this.intensity = 0,
    this.confidence = 0,
  });
  final String label;
  final double intensity;
  final double confidence;
  factory EmotionState.fromJson(Map<String, dynamic> j) => EmotionState(
    label: '${j['label'] ?? 'neutral'}',
    intensity: _d(j['intensity']),
    confidence: _d(j['confidence']),
  );
}

class IntentState {
  const IntentState({this.label = 'unknown', this.confidence = 0});
  final String label;
  final double confidence;
  factory IntentState.fromJson(Map<String, dynamic> j) => IntentState(
    label: '${j['label'] ?? 'unknown'}',
    confidence: _d(j['confidence']),
  );
}

class MemoryCandidate {
  const MemoryCandidate({
    this.id,
    this.key = '',
    this.value = '',
    this.confidence = 0,
    this.source = 'conversation',
  });
  final String? id;
  final String key, value, source;
  final double confidence;
  factory MemoryCandidate.fromJson(Map<String, dynamic> j) => MemoryCandidate(
    id: j['id']?.toString(),
    key: '${j['key'] ?? ''}',
    value: '${j['value'] ?? ''}',
    confidence: _d(j['confidence']),
    source: '${j['source'] ?? 'conversation'}',
  );
}

class VoiceState {
  const VoiceState({this.status = 'disabled', this.provider, this.confidence});
  final String status;
  final String? provider;
  final double? confidence;
  factory VoiceState.fromJson(Map<String, dynamic> j) => VoiceState(
    status: '${j['status'] ?? 'disabled'}',
    provider: j['provider']?.toString(),
    confidence: j['confidence'] == null ? null : _d(j['confidence']),
  );
}

class CompanionTurnResponse {
  const CompanionTurnResponse({
    this.text = '',
    this.turnId,
    this.conversationId,
    this.emotion = const EmotionState(),
    this.intent = const IntentState(),
    this.memories = const [],
    this.voiceInput = const VoiceState(),
    this.voiceOutput = const VoiceState(),
    this.stateRevision = 0,
  });
  final String text;
  final String? turnId, conversationId;
  final EmotionState emotion;
  final IntentState intent;
  final List<MemoryCandidate> memories;
  final VoiceState voiceInput, voiceOutput;
  final int stateRevision;
  factory CompanionTurnResponse.fromJson(Map<String, dynamic> j) =>
      CompanionTurnResponse(
        text: '${j['assistant_text'] ?? ''}',
        turnId: j['turn_id']?.toString(),
        conversationId: j['conversation_id']?.toString(),
        emotion: EmotionState.fromJson(
          Map<String, dynamic>.from(j['emotion'] ?? {}),
        ),
        intent: IntentState.fromJson(
          Map<String, dynamic>.from(j['intent'] ?? {}),
        ),
        memories: [
          for (final x in (j['memory_candidates'] as List? ?? const []))
            MemoryCandidate.fromJson(Map<String, dynamic>.from(x)),
        ],
        voiceInput: VoiceState.fromJson(
          Map<String, dynamic>.from(j['voice_input'] ?? {}),
        ),
        voiceOutput: VoiceState.fromJson(
          Map<String, dynamic>.from(j['voice_output'] ?? {}),
        ),
        stateRevision: int.tryParse('${j['state_revision'] ?? 0}') ?? 0,
      );
}

class GirlCharacter {
  const GirlCharacter({
    required this.id,
    required this.name,
    this.description = '',
    this.tags = const [],
  });
  final String id, name, description;
  final List<String> tags;
  factory GirlCharacter.fromJson(Map<String, dynamic> j) => GirlCharacter(
    id: '${j['id']}',
    name: '${j['name'] ?? j['id']}',
    description: '${j['description'] ?? ''}',
    tags: [for (final x in (j['tags'] as List? ?? const [])) '$x'],
  );
}

class GirlHistory {
  const GirlHistory({
    required this.id,
    required this.role,
    required this.content,
    this.createdAt,
  });
  final String id, role, content;
  final DateTime? createdAt;
  factory GirlHistory.fromJson(Map<String, dynamic> j) => GirlHistory(
    id: '${j['id']}',
    role: '${j['role'] ?? 'assistant'}',
    content: '${j['content'] ?? ''}',
    createdAt: DateTime.tryParse('${j['created_at'] ?? ''}'),
  );
}

class GirlPreference {
  const GirlPreference({
    required this.id,
    required this.key,
    required this.value,
  });
  final String id, key, value;
  factory GirlPreference.fromJson(Map<String, dynamic> j) => GirlPreference(
    id: '${j['id']}',
    key: '${j['key'] ?? j['preference_key'] ?? ''}',
    value: '${j['value'] ?? j['preference_value'] ?? ''}',
  );
}

double _d(dynamic v) => double.tryParse('$v') ?? 0;
