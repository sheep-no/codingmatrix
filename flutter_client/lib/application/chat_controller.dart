import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'auth_controller.dart';
import '../infrastructure/chat/chat_client.dart';
import '../domain/models/chat_models.dart';

class ChatState {
  const ChatState({
    this.messages = const [],
    this.loading = false,
    this.error,
    this.conversationId,
    this.history = const [],
    this.uploading = false,
    this.cancelled = false,
  });
  final List<ChatMessage> messages;
  final bool loading;
  final String? error;
  final int? conversationId;
  final List<ChatHistoryItem> history;
  final bool uploading;
  final bool cancelled;

  ChatState copyWith({
    List<ChatMessage>? messages,
    bool? loading,
    String? error,
    int? conversationId,
    List<ChatHistoryItem>? history,
    bool? uploading,
    bool? cancelled,
  }) {
    return ChatState(
      messages: messages ?? this.messages,
      loading: loading ?? this.loading,
      error: error,
      conversationId: conversationId ?? this.conversationId,
      history: history ?? this.history,
      uploading: uploading ?? this.uploading,
      cancelled: cancelled ?? this.cancelled,
    );
  }
}

class ChatController extends Notifier<ChatState> {
  StreamSubscription<ChatStreamEvent>? _subscription;
  Completer<void>? _completion;
  int _operation = 0;

  @override
  ChatState build() {
    ref.onDispose(_invalidate);
    return const ChatState();
  }

  void _invalidate() {
    _operation++;
    unawaited(_subscription?.cancel());
    _subscription = null;
    final completion = _completion;
    if (completion != null && !completion.isCompleted) completion.complete();
    _completion = null;
  }

  void cancel() {
    _invalidate();
    state = state.copyWith(loading: false, uploading: false, cancelled: true);
  }

  void reset() {
    _invalidate();
    state = const ChatState();
  }

  Future<void> loadHistory() async {
    final operation = _operation;
    try {
      final items = await ChatClient(
        ref.read(authenticatedClientProvider),
      ).history();
      if (operation != _operation) return;
      state = state.copyWith(history: items, error: null);
    } catch (error) {
      if (operation != _operation) return;
      state = state.copyWith(error: error.toString());
    }
  }

  Future<void> loadConversation(ChatHistoryItem item) async {
    _invalidate();
    final operation = _operation;
    state = state.copyWith(loading: true, uploading: false, cancelled: false);
    try {
      final messages = await ChatClient(
        ref.read(authenticatedClientProvider),
      ).detail(item.id);
      if (operation != _operation) return;
      state = state.copyWith(
        loading: false,
        messages: messages,
        conversationId: item.id,
        error: null,
      );
    } catch (error) {
      if (operation != _operation) return;
      state = state.copyWith(loading: false, error: error.toString());
    }
  }

  Future<void> send(
    String prompt, {
    String? model,
    bool reasoning = false,
    bool? search,
    List<Map<String, dynamic>>? files,
    List<String> filePaths = const [],
    bool streaming = false,
  }) async {
    final value = prompt.trim();
    if (value.isEmpty || state.loading) return;
    final operation = ++_operation;
    final completion = Completer<void>();
    _completion = completion;
    final messages = [
      ...state.messages,
      ChatMessage(text: value, fromUser: true),
    ];
    final conversationId = state.conversationId;
    state = state.copyWith(
      messages: messages,
      loading: true,
      error: null,
      cancelled: false,
      uploading: filePaths.isNotEmpty,
    );
    try {
      final api = ref.read(authenticatedClientProvider);
      final attachments = [...?files];
      for (final path in filePaths) {
        final uploaded = await Future.any<Map<String, dynamic>?>([
          api.uploadFile(path),
          completion.future.then((_) => null),
        ]);
        if (operation != _operation || uploaded == null) return;
        final serverPath = uploaded['server_path'];
        if (serverPath is! String || serverPath.trim().isEmpty) {
          throw const FormatException('上传响应缺少 server_path，无法发送附件');
        }
        attachments.add({
          'server_path': serverPath,
          'name': uploaded['name'] ?? path.split(RegExp(r'[/\\]')).last,
          'type': uploaded['type'] ?? 'application/octet-stream',
        });
      }
      if (operation != _operation) return;
      state = state.copyWith(uploading: false);
      final client = ChatClient(api);
      if (streaming) {
        var text = '';
        _subscription = client
            .streamEvents(
              prompt: value,
              conversationId: conversationId,
              model: model,
              reasoning: reasoning,
              search: search,
              files: attachments.isEmpty ? null : attachments,
            )
            .listen(
              (event) {
                if (operation != _operation || completion.isCompleted) return;
                text += event.text;
                state = state.copyWith(
                  conversationId: event.conversationId,
                  messages: [
                    ...messages,
                    if (text.isNotEmpty)
                      ChatMessage(text: text, fromUser: false),
                  ],
                  error: event.error,
                );
                if (event.error != null) {
                  completion.complete();
                  unawaited(_subscription?.cancel());
                }
              },
              onError: (Object error, StackTrace stack) {
                if (!completion.isCompleted) {
                  completion.completeError(error, stack);
                }
              },
              onDone: () {
                if (!completion.isCompleted) completion.complete();
              },
              cancelOnError: true,
            );
        await completion.future;
        if (operation != _operation) return;
        _subscription = null;
        _completion = null;
        state = state.copyWith(loading: false, error: state.error);
        return;
      }
      final reply = await Future.any<ChatReply?>([
        client.send(
          prompt: value,
          conversationId: conversationId,
          model: model,
          reasoning: reasoning,
          search: search,
          files: attachments.isEmpty ? null : attachments,
        ),
        completion.future.then((_) => null),
      ]);
      if (operation != _operation || reply == null) return;
      _completion = null;
      state = state.copyWith(
        loading: false,
        messages: [
          ...messages,
          ChatMessage(text: reply.text, fromUser: false),
        ],
        conversationId: reply.conversationId ?? conversationId,
      );
    } catch (error) {
      if (operation != _operation) return;
      _subscription = null;
      _completion = null;
      state = state.copyWith(
        loading: false,
        uploading: false,
        error: error.toString(),
      );
    }
  }
}

final chatControllerProvider = NotifierProvider<ChatController, ChatState>(
  ChatController.new,
);
