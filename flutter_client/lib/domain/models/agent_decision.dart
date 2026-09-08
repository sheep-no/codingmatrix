class AgentDecision {
  AgentDecision.fromJson(Map<String, dynamic> json)
    : id = json['id'] as String,
      question = json['question'] as String,
      context = json['context'] as String? ?? '',
      options = (json['options'] as List)
          .map((entry) => Map<String, String>.from(entry as Map))
          .toList(),
      defaultChoice = json['default'] as String?;

  final String id;
  final String question;
  final String context;
  final List<Map<String, String>> options;
  final String? defaultChoice;
}
