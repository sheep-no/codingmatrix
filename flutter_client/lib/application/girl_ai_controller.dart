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
    this.customCharacters = const [],
    this.memories = const [],
    this.preferences = const [],
    this.voiceInput,
    this.busyIds = const {},
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
  // User-owned custom characters, addressed by the backend `custom_<id>` prefix.
  final List<GirlCharacter> customCharacters;
  // Confirmed/candidate memories and preferences saved for this account.
  final List<CompanionMemory> memories;
  final List<GirlPreference> preferences;
  final VoiceState? voiceInput;
  // Ids of library rows (memory/preference/character) with an in-flight request.
  final Set<String> busyIds;
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
    List<GirlCharacter>? customCharacters,
    List<CompanionMemory>? memories,
    List<GirlPreference>? preferences,
    VoiceState? voiceInput,
    Set<String>? busyIds,
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
    customCharacters: customCharacters ?? this.customCharacters,
    memories: memories ?? this.memories,
    preferences: preferences ?? this.preferences,
    voiceInput: voiceInput ?? this.voiceInput,
    busyIds: busyIds ?? this.busyIds,
  );
}

final girlAiControllerProvider =
    NotifierProvider<GirlAiController, GirlAiState>(GirlAiController.new);

// Character avatars are served as SVG; fetch them through the authenticated
// client so tests and account switches go through the same transport.
final girlAvatarProvider = FutureProvider.autoDispose.family<String, String>(
  (ref, id) =>
      GirlAiClient(ref.read(authenticatedClientProvider)).avatarSvg(id),
);

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

  Future<void> send(String text) => _turn(text, voice: false);

  // The voice endpoint accepts a normalized transcription and runs it through
  // the same companion turn, surfacing `voice_input` on the response.
  Future<void> sendVoice(String text) => _turn(text, voice: true);

  Future<void> _turn(String text, {required bool voice}) async {
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
      final r = voice
          ? await api.transcribe(text.trim(), state.character)
          : await api.turn(text.trim(), state.character);
      if (g == _generation) {
        state = state.copyWith(
          loading: false,
          emotion: r.emotion,
          intent: r.intent,
          voiceInput: r.voiceInput,
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

  // Selecting a custom character also pins it into the picker so the main page
  // reflects the active role even though /characters only lists built-ins.
  void useCharacter(GirlCharacter character) {
    final characters = state.characters.any((x) => x.id == character.id)
        ? state.characters
        : [...state.characters, character];
    state = state.copyWith(characters: characters, character: character.id);
  }

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

  // ---- Custom characters -------------------------------------------------

  Future<void> loadCustomCharacters() async {
    final epoch = _epoch;
    try {
      final list = await api.customCharacters();
      if (epoch != _epoch) return;
      state = state.copyWith(
        customCharacters: [
          for (final c in list)
            GirlCharacter(
              id: 'custom_${c.id}',
              name: c.name,
              description: c.description,
              tags: c.tags,
              avatarColor: c.avatarColor,
            ),
        ],
        error: null,
      );
    } catch (e) {
      if (epoch != _epoch) return;
      state = state.copyWith(error: '$e');
    }
  }

  Future<bool> createCharacter(Map<String, dynamic> body) async {
    const key = 'character:create';
    if (state.busyIds.contains(key)) return false;
    final epoch = _epoch;
    state = state.copyWith(busyIds: {...state.busyIds, key});
    try {
      await api.createCharacter(body);
      if (epoch != _epoch) return false;
      await loadCustomCharacters();
      return epoch == _epoch;
    } catch (e) {
      if (epoch == _epoch) state = state.copyWith(error: '$e');
      return false;
    } finally {
      if (epoch == _epoch) {
        state = state.copyWith(
          error: state.error,
          busyIds: {...state.busyIds}..remove(key),
        );
      }
    }
  }

  Future<void> deleteCharacter(String id) async {
    if (state.busyIds.contains(id)) return;
    final epoch = _epoch;
    state = state.copyWith(busyIds: {...state.busyIds, id});
    try {
      const prefix = 'custom_';
      final raw = id.startsWith(prefix) ? id.substring(prefix.length) : id;
      await api.deleteCharacter(raw);
      if (epoch != _epoch) return;
      state = state.copyWith(
        customCharacters: state.customCharacters
            .where((c) => c.id != id)
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
          busyIds: {...state.busyIds}..remove(id),
        );
      }
    }
  }

  // ---- Saved memories and preferences ------------------------------------

  Future<void> loadMemories() async {
    final epoch = _epoch;
    try {
      final page = await api.memories();
      if (epoch != _epoch) return;
      state = state.copyWith(
        memories: [
          for (final x in (page['memories'] as List? ?? const []))
            CompanionMemory.fromJson(Map<String, dynamic>.from(x)),
        ],
        error: null,
      );
    } catch (e) {
      if (epoch != _epoch) return;
      state = state.copyWith(error: '$e');
    }
  }

  Future<void> removeMemory(String id) async {
    if (state.busyIds.contains(id)) return;
    final epoch = _epoch;
    state = state.copyWith(busyIds: {...state.busyIds, id});
    try {
      await api.deleteMemory(id);
      if (epoch != _epoch) return;
      state = state.copyWith(
        memories: state.memories.where((m) => m.id != id).toList(),
        memoryCandidates: state.memoryCandidates
            .where((m) => m.id != id)
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
          busyIds: {...state.busyIds}..remove(id),
        );
      }
    }
  }

  Future<void> loadPreferences() async {
    final epoch = _epoch;
    try {
      final data = await api.preferences();
      if (epoch != _epoch) return;
      state = state.copyWith(
        preferences: [
          for (final x in (data['preferences'] as List? ?? const []))
            GirlPreference.fromJson(Map<String, dynamic>.from(x)),
        ],
        error: null,
      );
    } catch (e) {
      if (epoch != _epoch) return;
      state = state.copyWith(error: '$e');
    }
  }

  Future<void> removePreference(String id) async {
    if (state.busyIds.contains(id)) return;
    final epoch = _epoch;
    state = state.copyWith(busyIds: {...state.busyIds, id});
    try {
      await api.deletePreference(id);
      if (epoch != _epoch) return;
      state = state.copyWith(
        preferences: state.preferences.where((p) => p.id != id).toList(),
        error: null,
      );
    } catch (e) {
      if (epoch != _epoch) return;
      state = state.copyWith(error: '$e');
    } finally {
      if (epoch == _epoch) {
        state = state.copyWith(
          error: state.error,
          busyIds: {...state.busyIds}..remove(id),
        );
      }
    }
  }

  // ---- History -----------------------------------------------------------

  Future<void> deleteHistoryRecords({
    List<String> ids = const [],
    bool all = false,
  }) async {
    if (!all && ids.isEmpty) return;
    final epoch = _epoch;
    try {
      await api.deleteHistory(ids: ids, all: all);
      if (epoch != _epoch) return;
      state = state.copyWith(
        history: all
            ? const []
            : state.history.where((r) => !ids.contains(r.id)).toList(),
        error: null,
      );
    } catch (e) {
      if (epoch != _epoch) return;
      state = state.copyWith(error: '$e');
    }
  }
}
