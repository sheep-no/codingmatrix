class ChatStreamEvent {
  const ChatStreamEvent({this.text = '', this.conversationId, this.error});

  final String text;
  final int? conversationId;
  final String? error;
}

class ChatReply {
  const ChatReply({required this.text, this.conversationId});

  final String text;
  final int? conversationId;

  factory ChatReply.fromJson(Map<String, dynamic> json) {
    return ChatReply(
      text: (json['response'] ?? '').toString(),
      conversationId: json['conversation_id'] as int?,
    );
  }
}

class ChatMessage {
  const ChatMessage({required this.text, required this.fromUser});
  final String text;
  final bool fromUser;
}

class ChatHistoryItem {
  const ChatHistoryItem({required this.id, required this.title});

  final int id;
  final String title;

  factory ChatHistoryItem.fromJson(Map<String, dynamic> json) {
    final id = (json['conversation_id'] ?? json['id']) as num;
    return ChatHistoryItem(
      id: id.toInt(),
      title: (json['prompt'] ?? json['title'] ?? '历史会话').toString(),
    );
  }
}
