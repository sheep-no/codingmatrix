import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/application/generation_flags_controller.dart';
import 'package:codingmatrix_desktop/domain/models/generation_flags.dart';
import 'package:codingmatrix_desktop/infrastructure/settings/capability_preferences.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'module_lifecycle_test.dart' show ModuleAuth;
import 'auth_session_test.dart' show Fixture;

class MemoryCapabilityPreferences implements CapabilityPreferences {
  final Map<String, Map<String, dynamic>> values = {};
  bool failRead = false;
  bool failWrite = false;

  @override
  Future<Map<String, dynamic>?> read(String scope) async {
    if (failRead) throw StateError('preferences-unavailable');
    return values[scope];
  }

  @override
  Future<void> write(String scope, Map<String, dynamic> value) async {
    if (failWrite) throw StateError('preferences-unavailable');
    values[scope] = value;
  }
}

const _scope = 'http://127.0.0.1:8080|alice';

void main() {
  test('没有已存值时使用默认开关', () async {
    final preferences = MemoryCapabilityPreferences();
    final controller = GenerationFlagsController(preferences, _scope);
    addTearDown(controller.dispose);

    await Future<void>.delayed(Duration.zero);

    expect(controller.state.enabledCount, 7);
  });

  test('载入已存值并按字段覆盖', () async {
    final preferences = MemoryCapabilityPreferences()
      ..values[_scope] = {'enable_skills': false, 'enable_memory': false};
    final controller = GenerationFlagsController(preferences, _scope);
    addTearDown(controller.dispose);

    await Future<void>.delayed(Duration.zero);

    expect(controller.state.enableSkills, isFalse);
    expect(controller.state.enableMemory, isFalse);
    expect(controller.state.enableReview, isTrue);
    expect(controller.state.enabledCount, 5);
  });

  test('切换开关会写入自身作用域', () async {
    final preferences = MemoryCapabilityPreferences();
    final controller = GenerationFlagsController(preferences, _scope);
    addTearDown(controller.dispose);

    controller.toggle(GenerationFlag.skills);
    await Future<void>.delayed(Duration.zero);

    expect(preferences.values.keys, [_scope]);
    expect(preferences.values[_scope]!['enable_skills'], isFalse);
  });

  test('作用域相互隔离', () async {
    final preferences = MemoryCapabilityPreferences()
      ..values['other'] = {'enable_skills': false};
    final controller = GenerationFlagsController(preferences, _scope);
    addTearDown(controller.dispose);

    await Future<void>.delayed(Duration.zero);

    expect(controller.state.enableSkills, isTrue);
  });

  test('读取失败回退默认值', () async {
    final preferences = MemoryCapabilityPreferences()..failRead = true;
    final controller = GenerationFlagsController(preferences, _scope);
    addTearDown(controller.dispose);

    await Future<void>.delayed(Duration.zero);

    expect(controller.state.enabledCount, 7);
  });

  test('写入失败保留内存中的开关', () async {
    final preferences = MemoryCapabilityPreferences()..failWrite = true;
    final controller = GenerationFlagsController(preferences, _scope);
    addTearDown(controller.dispose);

    controller.toggle(GenerationFlag.review);
    await Future<void>.delayed(Duration.zero);

    expect(controller.state.enableReview, isFalse);
  });

  test('账号切换载入新账号的开关', () async {
    final preferences = MemoryCapabilityPreferences()
      ..values['http://127.0.0.1:8080|bob'] = {'enable_skills': false};
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        capabilityPreferencesProvider.overrideWithValue(preferences),
      ],
    );
    addTearDown(container.dispose);

    container
        .read(generationFlagsControllerProvider.notifier)
        .toggle(GenerationFlag.memory);
    await Future<void>.delayed(Duration.zero);
    expect(preferences.values[_scope]!['enable_memory'], isFalse);

    auth.switchAccount('bob');
    // Reading the provider rebuilds it with the new scope; the load is async.
    container.read(generationFlagsControllerProvider);
    await Future<void>.delayed(Duration.zero);

    final bobFlags = container.read(generationFlagsControllerProvider);
    expect(bobFlags.enableSkills, isFalse);
    expect(bobFlags.enableMemory, isTrue);
  });
}
