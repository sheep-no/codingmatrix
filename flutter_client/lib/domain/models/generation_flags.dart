/// Generation switches sent with the orchestration request.
///
/// Field names match `OrchestratorRequest` in
/// `app/api/v1/ai_agent/schemas.py`; every switch defaults to `true`, which is
/// also the server default, so an untouched client keeps the old behavior.
class GenerationFlags {
  const GenerationFlags({
    this.enableReview = true,
    this.enableValidation = true,
    this.enableErrorRecovery = true,
    this.enableMemory = true,
    this.enableSkills = true,
    this.specFirst = true,
    this.dependencyGraph = true,
  });

  static const defaults = GenerationFlags();

  final bool enableReview;
  final bool enableValidation;
  final bool enableErrorRecovery;
  final bool enableMemory;
  final bool enableSkills;
  final bool specFirst;
  final bool dependencyGraph;

  int get enabledCount => [
    enableReview,
    enableValidation,
    enableErrorRecovery,
    enableMemory,
    enableSkills,
    specFirst,
    dependencyGraph,
  ].where((enabled) => enabled).length;

  GenerationFlags toggle(GenerationFlag flag) {
    return switch (flag) {
      GenerationFlag.review => copyWith(enableReview: !enableReview),
      GenerationFlag.validation => copyWith(
        enableValidation: !enableValidation,
      ),
      GenerationFlag.errorRecovery => copyWith(
        enableErrorRecovery: !enableErrorRecovery,
      ),
      GenerationFlag.memory => copyWith(enableMemory: !enableMemory),
      GenerationFlag.skills => copyWith(enableSkills: !enableSkills),
      GenerationFlag.specFirst => copyWith(specFirst: !specFirst),
      GenerationFlag.dependencyGraph => copyWith(
        dependencyGraph: !dependencyGraph,
      ),
    };
  }

  GenerationFlags copyWith({
    bool? enableReview,
    bool? enableValidation,
    bool? enableErrorRecovery,
    bool? enableMemory,
    bool? enableSkills,
    bool? specFirst,
    bool? dependencyGraph,
  }) {
    return GenerationFlags(
      enableReview: enableReview ?? this.enableReview,
      enableValidation: enableValidation ?? this.enableValidation,
      enableErrorRecovery: enableErrorRecovery ?? this.enableErrorRecovery,
      enableMemory: enableMemory ?? this.enableMemory,
      enableSkills: enableSkills ?? this.enableSkills,
      specFirst: specFirst ?? this.specFirst,
      dependencyGraph: dependencyGraph ?? this.dependencyGraph,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    'enable_review': enableReview,
    'enable_validation': enableValidation,
    'enable_error_recovery': enableErrorRecovery,
    'enable_memory': enableMemory,
    'enable_skills': enableSkills,
    'spec_first': specFirst,
    'dependency_graph': dependencyGraph,
  };

  factory GenerationFlags.fromJson(Map<String, dynamic> json) {
    bool read(String key) {
      final value = json[key];
      return value is bool ? value : true;
    }

    return GenerationFlags(
      enableReview: read('enable_review'),
      enableValidation: read('enable_validation'),
      enableErrorRecovery: read('enable_error_recovery'),
      enableMemory: read('enable_memory'),
      enableSkills: read('enable_skills'),
      specFirst: read('spec_first'),
      dependencyGraph: read('dependency_graph'),
    );
  }
}

enum GenerationFlag {
  review,
  validation,
  errorRecovery,
  memory,
  skills,
  specFirst,
  dependencyGraph,
}
