import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'auth_controller.dart';
import '../infrastructure/chat/chat_client.dart';
import '../domain/models/chat_models.dart';

const _unset = Object();

class ChatState {
  const ChatState({
    this.messages = const [],
    this.loading = false,
    this.loadingConversation = false,
    this.error,
    this.conversationId,
    this.history = const [],
    this.uploading = false,
    this.cancelled = false,
    this.stage,
  });
  final List<ChatMessage> messages;
  final bool loading;
  final bool loadingConversation;
  final String? error;
  final int? conversationId;
  final List<ChatHistoryItem> history;
  final bool uploading;
  final bool cancelled;
  final String? stage;

  ChatState copyWith({
    List<ChatMessage>? messages,
    bool? loading,
    bool? loadingConversation,
    String? error,
    int? conversationId,
    List<ChatHistoryItem>? history,
    bool? uploading,
    bool? cancelled,
    Object? stage = _unset,
  }) {
    return ChatState(
      messages: messages ?? this.messages,
      loading: loading ?? this.loading,
      loadingConversation: loadingConversation ?? this.loadingConversation,
      error: error,
      conversationId: conversationId ?? this.conversationId,
      history: history ?? this.history,
      uploading: uploading ?? this.uploading,
      cancelled: cancelled ?? this.cancelled,
      stage: identical(stage, _unset) ? this.stage : stage as String?,
    );
  }
}

class ChatController extends Notifier<ChatState> {
  StreamSubscription<ChatStreamEvent>? _subscription;
  Timer? _streamIdleTimer;
  Completer<void>? _completion;
  int _operation = 0;

  @override
  ChatState build() {
    ref.watch(
      authControllerProvider.select((auth) => auth.session?.accessTokenRef),
    );
    ref.onDispose(_invalidate);
    return const ChatState();
  }

  void _invalidate() {
    _operation++;
    _streamIdleTimer?.cancel();
    _streamIdleTimer = null;
    unawaited(_ignoreCancel(_subscription));
    _subscription = null;
    final completion = _completion;
    if (completion != null && !completion.isCompleted) completion.complete();
    _completion = null;
  }

  static Future<void> _ignoreCancel(
    StreamSubscription<ChatStreamEvent>? subscription,
  ) async {
    try {
      await subscription?.cancel();
    } catch (_) {
      // A broken stream can fail to cancel; the caller has already moved on.
    }
  }

  void cancel() {
    _invalidate();
    state = state.copyWith(
      loading: false,
      loadingConversation: false,
      uploading: false,
      cancelled: true,
      stage: null,
    );
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
    state = state.copyWith(
      loading: true,
      loadingConversation: true,
      uploading: false,
      cancelled: false,
      stage: null,
    );
    try {
      final messages = await ChatClient(
        ref.read(authenticatedClientProvider),
      ).detail(item.id);
      if (operation != _operation) return;
      state = state.copyWith(
        loading: false,
        loadingConversation: false,
        messages: messages,
        conversationId: item.id,
        error: null,
        stage: null,
      );
    } catch (error) {
      if (operation != _operation) return;
      state = state.copyWith(
        loading: false,
        loadingConversation: false,
        error: error.toString(),
        stage: null,
      );
    }
  }

  Future<void> send(
    String prompt, {
    String? model,
    String? apiKeyToken,
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
      loadingConversation: false,
      error: null,
      cancelled: false,
      uploading: filePaths.isNotEmpty,
      stage: null,
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
        // FileUploadResponse exposes the stored filename, never a server path:
        // Aicode.verify_file_access resolves attachments by file_path and falls
        // back to matching File.filename.
        final serverPath = uploaded['server_path'] ?? uploaded['filename'];
        if (serverPath is! String || serverPath.trim().isEmpty) {
          throw const FormatException('上传响应缺少文件名，无法发送附件');
        }
        final name = uploaded['name'] ?? uploaded['filename'];
        attachments.add({
          'server_path': serverPath,
          'name': name is String && name.trim().isNotEmpty
              ? name
              : path.split(RegExp(r'[/\\]')).last,
          'type':
              uploaded['type'] ??
              uploaded['content_type'] ??
              'application/octet-stream',
        });
      }
      if (operation != _operation) return;
      state = state.copyWith(uploading: false);
      final client = ChatClient(api);
      if (streaming) {
        var text = '';
        void armIdleTimer() {
          _streamIdleTimer?.cancel();
          _streamIdleTimer = Timer(
            reasoning
                ? const Duration(seconds: 180)
                : const Duration(seconds: 60),
            () {
              if (operation != _operation || completion.isCompleted) return;
              _streamIdleTimer = null;
              final stalled = _subscription;
              _subscription = null;
              _completion = null;
              unawaited(_ignoreCancel(stalled));
              state = state.copyWith(
                loading: false,
                loadingConversation: false,
                error: '等待回复超时，请稍后重试',
                stage: null,
              );
              completion.complete();
            },
          );
        }

        _subscription = client
            .streamEvents(
              prompt: value,
              conversationId: conversationId,
              model: model,
              apiKeyToken: apiKeyToken,
              reasoning: reasoning,
              search: search,
              files: attachments.isEmpty ? null : attachments,
            )
            .listen(
              (event) {
                armIdleTimer();
                if (operation != _operation || completion.isCompleted) return;
                text += event.text;
                state = state.copyWith(
                  conversationId: event.conversationId,
                  stage: event.text.isNotEmpty
                      ? null
                      : event.stage ?? state.stage,
                  messages: [
                    ...messages,
                    if (text.isNotEmpty)
                      ChatMessage(text: text, fromUser: false),
                  ],
                  error: event.error,
                );
                if (event.error != null) {
                  completion.complete();
                  unawaited(_ignoreCancel(_subscription));
                }
              },
              onError: (Object error, StackTrace stack) {
                _streamIdleTimer?.cancel();
                _streamIdleTimer = null;
                if (!completion.isCompleted) {
                  completion.completeError(error, stack);
                }
              },
              onDone: () {
                _streamIdleTimer?.cancel();
                _streamIdleTimer = null;
                if (!completion.isCompleted &&
                    operation == _operation &&
                    text.trim().isEmpty &&
                    state.error == null) {
                  state = state.copyWith(error: '模型没有返回内容，请重试', stage: null);
                }
                if (!completion.isCompleted) completion.complete();
              },
              cancelOnError: true,
            );
        armIdleTimer();
        await completion.future;
        _streamIdleTimer?.cancel();
        _streamIdleTimer = null;
        if (operation != _operation) return;
        _subscription = null;
        _completion = null;
        state = state.copyWith(
          loading: false,
          loadingConversation: false,
          error: state.error,
          stage: null,
        );
        return;
      }
      final reply = await Future.any<ChatReply?>([
        client.send(
          prompt: value,
          conversationId: conversationId,
          model: model,
          apiKeyToken: apiKeyToken,
          reasoning: reasoning,
          search: search,
          files: attachments.isEmpty ? null : attachments,
        ),
        completion.future.then((_) => null),
      ]);
      if (operation != _operation || reply == null) return;
      _completion = null;
      final text = reply.text.trim();
      state = state.copyWith(
        loading: false,
        loadingConversation: false,
        error: reply.error,
        messages: text.isEmpty
            ? messages
            : [...messages, ChatMessage(text: reply.text, fromUser: false)],
        conversationId: reply.conversationId ?? conversationId,
        stage: null,
      );
    } catch (error) {
      if (operation != _operation) return;
      _subscription = null;
      _completion = null;
      _streamIdleTimer?.cancel();
      _streamIdleTimer = null;
      final message = error is TimeoutException
          ? '等待回复超时，请稍后重试'
          : error.toString();
      state = state.copyWith(
        loading: false,
        loadingConversation: false,
        uploading: false,
        error: message,
        stage: null,
      );
    }
  }
}

final chatControllerProvider = NotifierProvider<ChatController, ChatState>(
  ChatController.new,
);
