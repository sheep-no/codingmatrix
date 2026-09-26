import 'package:codingmatrix_desktop/domain/models/generation_flags.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('默认七个开关全部启用', () {
    const flags = GenerationFlags.defaults;
    expect(flags.enabledCount, 7);
    expect(flags.toJson().values, everyElement(isTrue));
  });

  test('序列化字段名与后端 OrchestratorRequest 一致', () {
    expect(GenerationFlags.defaults.toJson().keys.toSet(), {
      'enable_review',
      'enable_validation',
      'enable_error_recovery',
      'enable_memory',
      'enable_skills',
      'spec_first',
      'dependency_graph',
    });
  });

  test('toggle 只改变目标开关', () {
    final flags = GenerationFlags.defaults.toggle(GenerationFlag.skills);
    expect(flags.enableSkills, isFalse);
    expect(flags.enabledCount, 6);
    expect(flags.enableReview, isTrue);
    expect(flags.enableValidation, isTrue);
    expect(flags.enableErrorRecovery, isTrue);
    expect(flags.enableMemory, isTrue);
    expect(flags.specFirst, isTrue);
    expect(flags.dependencyGraph, isTrue);
  });

  test('fromJson 对缺失或非布尔字段回退 true', () {
    final flags = GenerationFlags.fromJson({
      'enable_review': false,
      'enable_skills': 'no',
    });
    expect(flags.enableReview, isFalse);
    expect(flags.enableSkills, isTrue);
    expect(flags.enableValidation, isTrue);
    expect(flags.specFirst, isTrue);
  });

  test('toJson 与 fromJson 往返保持取值', () {
    final flags = GenerationFlags.defaults
        .toggle(GenerationFlag.memory)
        .toggle(GenerationFlag.dependencyGraph);
    final restored = GenerationFlags.fromJson(flags.toJson());
    expect(restored.toJson(), flags.toJson());
  });
}
