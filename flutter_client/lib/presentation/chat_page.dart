import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:file_picker/file_picker.dart';

import '../application/chat_controller.dart';

class ChatPage extends ConsumerStatefulWidget {
  const ChatPage({super.key});

  @override
  ConsumerState<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends ConsumerState<ChatPage> {
  final _controller = TextEditingController();
  final _modelController = TextEditingController();
  bool _reasoning = false;
  bool _search = false;
  final List<PlatformFile> _attachments = [];
  bool _picking = false;
  String? _attachmentError;
  int _sendVersion = 0;

  @override
  void dispose() {
    _controller.dispose();
    _modelController.dispose();
    super.dispose();
  }

  Future<void> _pickFiles() async {
    setState(() {
      _picking = true;
      _attachmentError = null;
    });
    try {
      final result = await FilePicker.platform.pickFiles(allowMultiple: true);
      if (!mounted || result == null) return;
      setState(() {
        for (final file in result.files) {
          if (file.path == null || file.path!.isEmpty) {
            _attachmentError = '无法读取 ${file.name} 的本地路径，请重新选择文件';
          } else if (!_attachments.any((item) => item.path == file.path)) {
            _attachments.add(file);
          }
        }
      });
    } catch (error) {
      if (mounted) setState(() => _attachmentError = '文件选择失败：$error');
    } finally {
      if (mounted) setState(() => _picking = false);
    }
  }

  Future<void> _send() async {
    final text = _controller.text.trim();
    if (text.isEmpty || _picking || ref.read(chatControllerProvider).loading) {
      return;
    }
    final version = ++_sendVersion;
    setState(() => _attachmentError = null);
    await ref
        .read(chatControllerProvider.notifier)
        .send(
          text,
          model: _modelController.text.trim().isEmpty
              ? null
              : _modelController.text.trim(),
          reasoning: _reasoning,
          search: _search,
          filePaths: _attachments.map((file) => file.path!).toList(),
          streaming: true,
        );
    if (!mounted || version != _sendVersion) return;
    final state = ref.read(chatControllerProvider);
    if (state.error == null && !state.cancelled) {
      _controller.clear();
      setState(() => _attachments.clear());
    }
  }

  @override
  Widget build(BuildContext context) {
    final chat = ref.watch(chatControllerProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('聊天'),
        actions: [
          IconButton(
            key: const Key('newChatButton'),
            tooltip: '新会话',
            onPressed: chat.loading
                ? null
                : () {
                    _sendVersion++;
                    ref.read(chatControllerProvider.notifier).reset();
                  },
            icon: const Icon(Icons.add_comment_outlined),
          ),
          IconButton(
            key: const Key('chatHistoryButton'),
            tooltip: '历史会话',
            onPressed: chat.loading ? null : _showHistory,
            icon: const Icon(Icons.history),
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: chat.messages.length,
              itemBuilder: (context, index) {
                final message = chat.messages[index];
                return Align(
                  alignment: message.fromUser
                      ? Alignment.centerRight
                      : Alignment.centerLeft,
                  child: Card(
                    color: message.fromUser
                        ? Theme.of(context).colorScheme.primaryContainer
                        : null,
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: SelectableText(message.text),
                    ),
                  ),
                );
              },
            ),
          ),
          if (chat.error != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                chat.error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          if (_attachmentError != null)
            Text(
              _attachmentError!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          if (chat.loading) Text(chat.uploading ? '正在上传附件…' : '正在接收回复…'),
          if (chat.cancelled) const Text('已取消，已接收的内容已保留'),
          if (_attachments.isNotEmpty)
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 120),
              child: SingleChildScrollView(
                child: Wrap(
                  spacing: 8,
                  children: _attachments
                      .map(
                        (file) => InputChip(
                          label: Text(file.name),
                          onDeleted: chat.loading
                              ? null
                              : () => setState(() => _attachments.remove(file)),
                        ),
                      )
                      .toList(),
                ),
              ),
            ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                IconButton(
                  key: const Key('chatAttachButton'),
                  tooltip: '添加附件',
                  onPressed: chat.loading || _picking ? null : _pickFiles,
                  icon: const Icon(Icons.attach_file),
                ),
                Expanded(
                  child: TextField(
                    key: const Key('chatPromptField'),
                    controller: _controller,
                    enabled: !chat.loading,
                    minLines: 1,
                    maxLines: 4,
                    onSubmitted: (_) => _send(),
                    decoration: const InputDecoration(labelText: '输入消息'),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton(
                  key: const Key('chatSendButton'),
                  tooltip: chat.loading ? '取消发送' : '发送',
                  onPressed: chat.loading
                      ? () {
                          _sendVersion++;
                          ref.read(chatControllerProvider.notifier).cancel();
                        }
                      : _picking
                      ? null
                      : _send,
                  icon: Icon(chat.loading ? Icons.stop : Icons.send),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            child: Wrap(
              spacing: 12,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                SizedBox(
                  width: 180,
                  child: TextField(
                    key: const Key('chatModelField'),
                    controller: _modelController,
                    decoration: const InputDecoration(labelText: '模型（可选）'),
                  ),
                ),
                FilterChip(
                  label: const Text('深度推理'),
                  selected: _reasoning,
                  onSelected: chat.loading
                      ? null
                      : (value) => setState(() => _reasoning = value),
                ),
                FilterChip(
                  label: const Text('联网搜索'),
                  selected: _search,
                  onSelected: chat.loading
                      ? null
                      : (value) => setState(() => _search = value),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _showHistory() async {
    await ref.read(chatControllerProvider.notifier).loadHistory();
    if (!mounted) return;
    final history = ref.read(chatControllerProvider).history;
    await showModalBottomSheet<void>(
      context: context,
      builder: (sheetContext) => SafeArea(
        child: ListView(
          children: history.isEmpty
              ? [const ListTile(title: Text('暂无历史会话'))]
              : history
                    .map(
                      (item) => ListTile(
                        title: Text(
                          item.title,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        onTap: () async {
                          Navigator.pop(sheetContext);
                          await ref
                              .read(chatControllerProvider.notifier)
                              .loadConversation(item);
                        },
                      ),
                    )
                    .toList(),
        ),
      ),
    );
  }
}
