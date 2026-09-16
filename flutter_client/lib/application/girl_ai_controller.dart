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
    this.busyMemoryIds = const {},
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
  // Ids of memory candidates with an in-flight confirm/delete request.
  final Set<String> busyMemoryIds;
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
    Set<String>? busyMemoryIds,
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
    busyMemoryIds: busyMemoryIds ?? this.busyMemoryIds,
    history: history ?? this.history,
  );
}

final girlAiControllerProvider =
    NotifierProvider<GirlAiController, GirlAiState>(GirlAiController.new);

class GirlAiController extends Notifier<GirlAiState> {
  int _generation = 0;
  // Bumped when this notifier's scope is torn down (account switch or scope
  // disposal). Requests started under the previous scope must not write into
  // the new one, and this notifier instance is reused across rebuilds, so a
  // one-way flag would stay latched and mute every later request.
  int _epoch = 0;
  GirlAiClient get api => GirlAiClient(ref.read(authenticatedClientProvider));
  @override
  GirlAiState build() {
    ref.watch(
      authControllerProvider.select((auth) => auth.session?.accessTokenRef),
    );
    ref.onDispose(() {
      _generation++;
      _epoch++;
    });
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
    final epoch = _epoch;
    try {
      final records = query == null || query.trim().isEmpty
          ? await api.history()
          : await api.search(query.trim());
      if (epoch != _epoch) return;
      state = state.copyWith(history: records, error: null);
    } catch (e) {
      if (epoch != _epoch) return;
      state = state.copyWith(error: '$e');
    }
  }

  Future<void> confirmMemory(MemoryCandidate memory) async {
    final id = memory.id;
    if (id == null || state.busyMemoryIds.contains(id)) return;
    final epoch = _epoch;
    state = state.copyWith(busyMemoryIds: {...state.busyMemoryIds, id});
    try {
      await api.confirmMemory(id, key: memory.key, value: memory.value);
      if (epoch != _epoch) return;
      state = state.copyWith(
        memoryCandidates: state.memoryCandidates
            .where((item) => item.id != id)
            .toList(),
        error: null,
      );
    } catch (e) {
      if (epoch != _epoch) return;
      state = state.copyWith(error: '$e');
    } finally {
      if (epoch == _epoch) {
        state = state.copyWith(
          error: state.error,
          busyMemoryIds: {...state.busyMemoryIds}..remove(id),
        );
      }
    }
  }

  Future<void> deleteMemory(MemoryCandidate memory) async {
    final id = memory.id;
    if (id == null || state.busyMemoryIds.contains(id)) return;
    final epoch = _epoch;
    state = state.copyWith(busyMemoryIds: {...state.busyMemoryIds, id});
    try {
      await api.deleteMemory(id);
      if (epoch != _epoch) return;
      state = state.copyWith(
        memoryCandidates: state.memoryCandidates
            .where((item) => item.id != id)
            .toList(),
        error: null,
      );
    } catch (e) {
      if (epoch != _epoch) return;
      state = state.copyWith(error: '$e');
    } finally {
      if (epoch == _epoch) {
        state = state.copyWith(
          error: state.error,
          busyMemoryIds: {...state.busyMemoryIds}..remove(id),
        );
      }
    }
  }
}
