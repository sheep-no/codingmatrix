class ChatStreamEvent {
  const ChatStreamEvent({
    this.text = '',
    this.conversationId,
    this.error,
    this.stage,
  });

  final String text;
  final int? conversationId;
  final String? error;
  final String? stage;
}

class ChatReply {
  const ChatReply({required this.text, this.conversationId, this.error});

  final String text;
  final int? conversationId;
  final String? error;

  factory ChatReply.fromJson(Map<String, dynamic> json) {
    return ChatReply(
      text: (json['response'] ?? '').toString(),
      conversationId: json['conversation_id'] as int?,
      // The backend answers with HTTP 200 plus an `error` when it produced no
      // reply (e.g. an empty model response); dropping it would leave the user
      // with a blank assistant bubble and no explanation.
      error: json['error'] == null ? null : '${json['error']}',
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
    final raw = json['conversation_id'] ?? json['id'];
    final id = raw is num ? raw.toInt() : int.tryParse('$raw');
    if (id == null) {
      throw const FormatException('历史会话缺少有效的 conversation_id');
    }
    return ChatHistoryItem(
      id: id,
      title: (json['prompt'] ?? json['title'] ?? '历史会话').toString(),
    );
  }
}
