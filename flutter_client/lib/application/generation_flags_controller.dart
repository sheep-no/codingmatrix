import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../domain/models/generation_flags.dart';
import '../infrastructure/settings/capability_preferences.dart';
import 'auth_controller.dart';

class GenerationFlagsController extends StateNotifier<GenerationFlags> {
  GenerationFlagsController(this.preferences, this.scope)
    : super(GenerationFlags.defaults) {
    if (scope != null) {
      unawaited(_load());
    }
  }

  final CapabilityPreferences preferences;
  final String? scope;
  bool _touched = false;

  Future<void> _load() async {
    final scope = this.scope;
    if (scope == null) return;
    try {
      final stored = await preferences.read(scope);
      // A toggle before the load finished is newer than what is on disk.
      if (!mounted || _touched || stored == null) return;
      state = GenerationFlags.fromJson(stored);
    } catch (_) {
      // The defaults match the server defaults, so the request stays valid.
    }
  }

  void toggle(GenerationFlag flag) {
    _touched = true;
    state = state.toggle(flag);
    final scope = this.scope;
    if (scope == null) return;
    unawaited(
      preferences.write(scope, state.toJson()).catchError((Object _) {
        // The in-memory value still applies to this session.
      }),
    );
  }
}

final generationFlagsControllerProvider =
    StateNotifierProvider<GenerationFlagsController, GenerationFlags>((ref) {
      final session = ref.watch(
        authControllerProvider.select((auth) => auth.session),
      );
      final baseUrl = ref.watch(apiBaseUrlProvider);
      return GenerationFlagsController(
        ref.watch(capabilityPreferencesProvider),
        session == null ? null : '$baseUrl|${session.username}',
      );
    });
