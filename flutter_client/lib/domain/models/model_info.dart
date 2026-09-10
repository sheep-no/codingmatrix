class ModelInfo {
  const ModelInfo({
    required this.id,
    required this.name,
    required this.modelKey,
    required this.description,
    this.capabilities = const [],
    this.tags = const [],
    this.isDefault = false,
  });
  final String id, name, modelKey, description;
  final List<String> capabilities, tags;
  final bool isDefault;
  factory ModelInfo.fromJson(Map<String, dynamic> json) => ModelInfo(
    id: '${json['id']}',
    name: '${json['name'] ?? json['id']}',
    modelKey: '${json['model_key'] ?? ''}',
    description: '${json['description'] ?? ''}',
    capabilities: [
      for (final x in (json['capabilities'] as List? ?? const [])) '$x',
    ],
    tags: [for (final x in (json['tags'] as List? ?? const [])) '$x'],
    isDefault: json['is_default'] == true,
  );
}
