import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'auth_controller.dart';
import '../domain/models/girl_companion.dart';
import '../infrastructure/girl/girl_ai_client.dart';

class GirlAiState {
  const GirlAiState({
    this.character = 'gentle',
    this.messages = const [],
    this.characters = const [],
    this.loading = false,
    this.error,
    this.emotion,
    this.intent,
    this.memoryCandidates = const [],
    this.history = const [],
  });
  final String character;
  final List<GirlHistory> messages;
  final List<GirlCharacter> characters;
  final bool loading;
  final String? error;
  final EmotionState? emotion;
  final IntentState? intent;
  final List<MemoryCandidate> memoryCandidates;
  final List<GirlHistory> history;
  GirlAiState copyWith({
    String? character,
    List<GirlHistory>? messages,
    List<GirlCharacter>? characters,
    bool? loading,
    String? error,
    EmotionState? emotion,
    IntentState? intent,
    List<MemoryCandidate>? memoryCandidates,
    List<GirlHistory>? history,
  }) => GirlAiState(
    character: character ?? this.character,
    messages: messages ?? this.messages,
    characters: characters ?? this.characters,
    loading: loading ?? this.loading,
    error: error,
    emotion: emotion ?? this.emotion,
    intent: intent ?? this.intent,
    memoryCandidates: memoryCandidates ?? this.memoryCandidates,
    history: history ?? this.history,
  );
}

final girlAiControllerProvider =
    NotifierProvider<GirlAiController, GirlAiState>(GirlAiController.new);

class GirlAiController extends Notifier<GirlAiState> {
  int _generation = 0;
  GirlAiClient get api => GirlAiClient(ref.read(authenticatedClientProvider));
  @override
  GirlAiState build() {
    ref.onDispose(() => _generation++);
    return const GirlAiState();
  }

  Future<void> load() async {
    final g = ++_generation;
    state = state.copyWith(loading: true, error: null);
    try {
      final c = await api.characters();
      if (g == _generation) {
        state = state.copyWith(characters: c, loading: false);
      }
    } catch (e) {
      if (g == _generation) state = state.copyWith(loading: false, error: '$e');
    }
  }

  Future<void> send(String text) async {
    if (text.trim().isEmpty || state.loading) return;
    final g = ++_generation;
    state = state.copyWith(
      loading: true,
      error: null,
      messages: [
        ...state.messages,
        GirlHistory(id: 'local', role: 'user', content: text),
      ],
    );
    try {
      final r = await api.turn(text.trim(), state.character);
      if (g == _generation) {
        state = state.copyWith(
          loading: false,
          emotion: r.emotion,
          intent: r.intent,
          memoryCandidates: r.memories,
          messages: [
            ...state.messages,
            GirlHistory(
              id: r.turnId ?? 'local',
              role: 'assistant',
              content: r.text,
            ),
          ],
        );
      }
    } catch (e) {
      if (g == _generation) state = state.copyWith(loading: false, error: '$e');
    }
  }

  void select(String id) => state = state.copyWith(character: id);

  Future<void> loadHistory({String? query}) async {
    try {
      final records = query == null || query.trim().isEmpty
          ? await api.history()
          : await api.search(query.trim());
      state = state.copyWith(history: records, error: null);
    } catch (e) {
      state = state.copyWith(error: '$e');
    }
  }

  Future<void> confirmMemory(MemoryCandidate memory) async {
    if (memory.id == null) return;
    try {
      await api.confirmMemory(memory.id!, key: memory.key, value: memory.value);
      state = state.copyWith(
        memoryCandidates: state.memoryCandidates
            .where((item) => item.id != memory.id)
            .toList(),
        error: null,
      );
    } catch (e) {
      state = state.copyWith(error: '$e');
    }
  }

  Future<void> deleteMemory(MemoryCandidate memory) async {
    if (memory.id == null) return;
    try {
      await api.deleteMemory(memory.id!);
      state = state.copyWith(
        memoryCandidates: state.memoryCandidates
            .where((item) => item.id != memory.id)
            .toList(),
        error: null,
      );
    } catch (e) {
      state = state.copyWith(error: '$e');
    }
  }
}
