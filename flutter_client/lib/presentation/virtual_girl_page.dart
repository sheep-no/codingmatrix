import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../application/auth_controller.dart';
import '../application/girl_ai_controller.dart';
import '../domain/models/girl_companion.dart';
import 'account_overlays.dart';
import 'model_service_hint.dart';
import 'shell_scaffold.dart';

class VirtualGirlPage extends ConsumerStatefulWidget {
  const VirtualGirlPage({super.key});
  @override
  ConsumerState<VirtualGirlPage> createState() => _VirtualGirlPageState();
}

class _VirtualGirlPageState extends ConsumerState<VirtualGirlPage> {
  final input = TextEditingController();
  bool historyBusy = false;
  bool libraryBusy = false;
  bool voiceMode = false;
  // Bumped on account change so an in-flight library request does not open a
  // sheet over the next account.
  int _epoch = 0;
  @override
  void initState() {
    super.initState();
    Future.microtask(() => ref.read(girlAiControllerProvider.notifier).load());
  }

  @override
  void dispose() {
    input.dispose();
    super.dispose();
  }

  void _send() {
    final value = input.text.trim();
    // Enter bypasses the disabled send button, so keep the draft whenever the
    // controller would refuse it (an in-flight reply already owns the turn).
    if (value.isEmpty || ref.read(girlAiControllerProvider).loading) return;
    input.clear();
    final controller = ref.read(girlAiControllerProvider.notifier);
    if (voiceMode) {
      controller.sendVoice(value);
    } else {
      controller.send(value);
    }
  }

  void _resetAccount() {
    _epoch++;
    closeAccountOverlays(context);
    input.clear();
    // The account-scoped controller drops its role list on rebuild, so fetch
    // it again for the account that just became active.
    ref.read(girlAiControllerProvider.notifier).load();
  }

  Future<void> _showHistory() async {
    if (historyBusy) return;
    final epoch = _epoch;
    setState(() => historyBusy = true);
    try {
      await ref.read(girlAiControllerProvider.notifier).loadHistory();
      if (!mounted || epoch != _epoch) return;
      await showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        isDismissible: true,
        enableDrag: true,
        useSafeArea: true,
        showDragHandle: true,
        barrierLabel: '关闭历史记录',
        builder: (_) => const _HistorySheet(),
      );
    } finally {
      if (mounted) setState(() => historyBusy = false);
    }
  }

  Future<void> _showCharacters() async {
    if (libraryBusy) return;
    final epoch = _epoch;
    setState(() => libraryBusy = true);
    try {
      await showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        isDismissible: true,
        enableDrag: true,
        useSafeArea: true,
        showDragHandle: true,
        barrierLabel: '关闭角色库',
        builder: (_) => const _CharacterSheet(),
      );
      if (!mounted || epoch != _epoch) return;
    } finally {
      if (mounted) setState(() => libraryBusy = false);
    }
  }

  Future<void> _showMemories() async {
    if (libraryBusy) return;
    final epoch = _epoch;
    setState(() => libraryBusy = true);
    try {
      final controller = ref.read(girlAiControllerProvider.notifier);
      await Future.wait([
        controller.loadMemories(),
        controller.loadPreferences(),
      ]);
      if (!mounted || epoch != _epoch) return;
      await showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        isDismissible: true,
        enableDrag: true,
        useSafeArea: true,
        showDragHandle: true,
        barrierLabel: '关闭记忆库',
        builder: (_) => const _MemorySheet(),
      );
    } finally {
      if (mounted) setState(() => libraryBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(
      authControllerProvider.select((s) => s.session?.accessTokenRef),
      (_, __) => _resetAccount(),
    );
    ref.listen(apiBaseUrlProvider, (_, __) => _resetAccount());
    final state = ref.watch(girlAiControllerProvider);
    return ShellScaffold(
      title: '虚拟姬',
      actions: [
        IconButton(
          tooltip: '角色库',
          onPressed: libraryBusy ? null : _showCharacters,
          icon: const Icon(Icons.face_retouching_natural),
        ),
        IconButton(
          tooltip: '记忆库',
          onPressed: libraryBusy ? null : _showMemories,
          icon: const Icon(Icons.psychology),
        ),
        IconButton(
          tooltip: '历史记录',
          onPressed: historyBusy ? null : _showHistory,
          icon: const Icon(Icons.history),
        ),
      ],
      body: SafeArea(
        child: Column(
          children: [
            if (state.characters.isNotEmpty)
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: [
                    for (final character in state.characters)
                      Padding(
                        padding: const EdgeInsets.all(4),
                        child: ChoiceChip(
                          label: Text(character.name),
                          selected: state.character == character.id,
                          onSelected: (_) => ref
                              .read(girlAiControllerProvider.notifier)
                              .select(character.id),
                        ),
                      ),
                  ],
                ),
              ),
            if (state.emotion != null || state.intent != null)
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 4,
                ),
                child: Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  children: [
                    if (state.emotion != null)
                      Chip(label: Text('情绪: ${state.emotion!.label}')),
                    if (state.intent != null)
                      Chip(label: Text('意图: ${state.intent!.label}')),
                    if (state.voiceInput?.status == 'received')
                      const Chip(label: Text('语音已识别')),
                  ],
                ),
              ),
            Expanded(
              child: state.loading && state.messages.isEmpty
                  ? const Center(child: CircularProgressIndicator())
                  : state.error != null &&
                        state.messages.isEmpty &&
                        state.characters.isEmpty
                  ? _PageFailure(
                      error: state.error!,
                      onRetry: () =>
                          ref.read(girlAiControllerProvider.notifier).load(),
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.all(16),
                      itemCount: state.messages.length,
                      itemBuilder: (context, index) {
                        final message = state.messages[index];
                        return Align(
                          alignment: message.role == 'user'
                              ? Alignment.centerRight
                              : Alignment.centerLeft,
                          child: Card(
                            child: Padding(
                              padding: const EdgeInsets.all(12),
                              child: Text(message.content),
                            ),
                          ),
                        );
                      },
                    ),
            ),
            if (state.error != null &&
                !(state.messages.isEmpty && state.characters.isEmpty))
              Padding(
                padding: const EdgeInsets.all(8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    ModelServiceHint(error: state.error!),
                    if (state.canRetryTurn)
                      TextButton.icon(
                        key: const Key('girlRetryTurnButton'),
                        onPressed: state.loading
                            ? null
                            : () => ref
                                  .read(girlAiControllerProvider.notifier)
                                  .retryLastTurn(),
                        icon: const Icon(Icons.refresh),
                        label: const Text('点击重试'),
                      ),
                  ],
                ),
              ),
            for (final memory in state.memoryCandidates)
              Card(
                margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 3),
                child: ListTile(
                  dense: true,
                  title: Text('${memory.key}: ${memory.value}'),
                  subtitle: const Text('发现一条可保存的记忆'),
                  trailing: Wrap(
                    children: [
                      IconButton(
                        tooltip: '保存',
                        onPressed: state.busyMemoryIds.contains(memory.id)
                            ? null
                            : () => ref
                                  .read(girlAiControllerProvider.notifier)
                                  .confirmMemory(memory),
                        icon: const Icon(Icons.check),
                      ),
                      IconButton(
                        tooltip: '忽略',
                        onPressed: state.busyMemoryIds.contains(memory.id)
                            ? null
                            : () => ref
                                  .read(girlAiControllerProvider.notifier)
                                  .deleteMemory(memory),
                        icon: const Icon(Icons.close),
                      ),
                    ],
                  ),
                ),
              ),
            if (voiceMode)
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 12),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text('语音模式：发送将按语音转写处理'),
                ),
              ),
            Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  IconButton(
                    tooltip: voiceMode ? '退出语音模式' : '语音输入',
                    isSelected: voiceMode,
                    onPressed: state.loading
                        ? null
                        : () => setState(() => voiceMode = !voiceMode),
                    icon: const Icon(Icons.mic),
                  ),
                  Expanded(
                    child: TextField(
                      controller: input,
                      onSubmitted: (_) => _send(),
                      decoration: const InputDecoration(hintText: '和虚拟姬聊天'),
                    ),
                  ),
                  IconButton(
                    onPressed: state.loading ? null : _send,
                    icon: const Icon(Icons.send),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PageFailure extends StatelessWidget {
  const _PageFailure({required this.error, required this.onRetry});

  final String error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.cloud_off,
              size: 44,
              color: theme.colorScheme.onSurfaceVariant,
            ),
            const SizedBox(height: 12),
            Text('伴侣服务暂时不可用', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(
              '上游服务没有响应，你可以稍后重试；其他模块仍可正常使用。',
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                error,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall,
              ),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              key: const Key('girlPageRetryButton'),
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('重试'),
            ),
            if (isModelServiceFailure(error)) ...[
              const SizedBox(height: 12),
              ModelServiceHint(error: error),
            ],
          ],
        ),
      ),
    );
  }
}

class _LibraryEmpty extends StatelessWidget {
  const _LibraryEmpty({
    required this.icon,
    required this.title,
    required this.subtitle,
    this.onRetry,
    this.compact = false,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback? onRetry;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: 24,
        vertical: compact ? 16 : 32,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            icon,
            size: compact ? 28 : 40,
            color: theme.colorScheme.onSurfaceVariant,
          ),
          const SizedBox(height: 8),
          Text(title, style: theme.textTheme.titleSmall),
          const SizedBox(height: 4),
          Text(
            subtitle,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          if (onRetry != null) ...[
            const SizedBox(height: 8),
            TextButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('重新加载'),
            ),
          ],
        ],
      ),
    );
  }
}

class _HistorySheet extends ConsumerStatefulWidget {
  const _HistorySheet();
  @override
  ConsumerState<_HistorySheet> createState() => _HistorySheetState();
}

class _HistorySheetState extends ConsumerState<_HistorySheet> {
  final query = TextEditingController();
  bool busy = false;

  @override
  void dispose() {
    query.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action) async {
    if (busy) return;
    setState(() => busy = true);
    try {
      await action();
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _clearAll() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('清空历史记录'),
        content: const Text('将删除当前账号的全部虚拟姬对话历史，且无法恢复。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('清空'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    await _run(
      () => ref
          .read(girlAiControllerProvider.notifier)
          .deleteHistoryRecords(all: true),
    );
  }

  @override
  Widget build(BuildContext context) {
    final records = ref.watch(girlAiControllerProvider).history;
    final controller = ref.read(girlAiControllerProvider.notifier);
    return SafeArea(
      child: SizedBox(
        height: MediaQuery.sizeOf(context).height * 0.7,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: query,
                      onSubmitted: (_) =>
                          _run(() => controller.loadHistory(query: query.text)),
                      decoration: const InputDecoration(
                        isDense: true,
                        prefixIcon: Icon(Icons.search),
                        labelText: '搜索历史记录',
                        hintText: '搜索历史记录',
                        helperText: '输入关键词后回车搜索',
                      ),
                    ),
                  ),
                  Tooltip(
                    message: records.isEmpty ? '暂无记录可清空' : '清空全部历史记录',
                    child: TextButton(
                      onPressed: records.isEmpty || busy ? null : _clearAll,
                      child: const Text('清空'),
                    ),
                  ),
                ],
              ),
            ),
            if (records.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    '暂无可清空的记录',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
              ),
            Expanded(
              child: records.isEmpty
                  ? const _LibraryEmpty(
                      icon: Icons.history,
                      title: '暂无历史记录',
                      subtitle: '完成一次对话后，记录会出现在这里',
                    )
                  : ListView.builder(
                      itemCount: records.length,
                      itemBuilder: (_, index) {
                        final item = records[index];
                        return ListTile(
                          title: Text(item.content),
                          subtitle: Text(item.role),
                          trailing: IconButton(
                            tooltip: '删除记录',
                            onPressed: busy
                                ? null
                                : () => _run(
                                    () => controller.deleteHistoryRecords(
                                      ids: [item.id],
                                    ),
                                  ),
                            icon: const Icon(Icons.delete_outline),
                          ),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CharacterSheet extends ConsumerStatefulWidget {
  const _CharacterSheet();
  @override
  ConsumerState<_CharacterSheet> createState() => _CharacterSheetState();
}

class _CharacterSheetState extends ConsumerState<_CharacterSheet> {
  @override
  void initState() {
    super.initState();
    Future.microtask(_reload);
  }

  Future<void> _reload() async {
    final controller = ref.read(girlAiControllerProvider.notifier);
    if (ref.read(girlAiControllerProvider).characters.isEmpty) {
      await controller.load();
    }
    await controller.loadCustomCharacters();
  }

  Future<void> _create() async {
    await showDialog<bool>(
      context: context,
      builder: (_) => const _CreateCharacterDialog(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(girlAiControllerProvider);
    final controller = ref.read(girlAiControllerProvider.notifier);
    final builtIns = state.characters
        .where((c) => !c.id.startsWith('custom_'))
        .toList();
    final loading = state.loading || state.customCharactersLoading;
    final empty = builtIns.isEmpty && state.customCharacters.isEmpty;
    return SafeArea(
      child: SizedBox(
        height: MediaQuery.sizeOf(context).height * 0.7,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 8, 0),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      '角色库',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                  ),
                  IconButton(
                    tooltip: '关闭角色库',
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close),
                  ),
                  TextButton.icon(
                    onPressed: state.busyIds.contains('character:create')
                        ? null
                        : _create,
                    icon: const Icon(Icons.add),
                    label: const Text('新建角色'),
                  ),
                ],
              ),
            ),
            Expanded(
              child: loading && empty
                  ? const Center(child: CircularProgressIndicator())
                  : empty
                  ? _LibraryEmpty(
                      icon: Icons.face_retouching_natural,
                      title: '暂无可用角色',
                      subtitle: state.error == null
                          ? '还没有内置或自定义角色，可以新建一个角色开始对话'
                          : '角色加载失败：${state.error}',
                      onRetry: _reload,
                    )
                  : ListView(
                      children: [
                        for (final character in builtIns)
                          _CharacterTile(
                            character: character,
                            selected: state.character == character.id,
                            onUse: () {
                              controller.useCharacter(character);
                              Navigator.of(context).pop();
                            },
                          ),
                        if (state.customCharacters.isNotEmpty) ...[
                          const Divider(height: 1),
                          for (final character in state.customCharacters)
                            _CharacterTile(
                              character: character,
                              selected: state.character == character.id,
                              onUse: () {
                                controller.useCharacter(character);
                                Navigator.of(context).pop();
                              },
                              onDelete: state.busyIds.contains(character.id)
                                  ? null
                                  : () => controller.deleteCharacter(
                                      character.id,
                                    ),
                            ),
                        ],
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CharacterTile extends ConsumerWidget {
  const _CharacterTile({
    required this.character,
    required this.selected,
    required this.onUse,
    this.onDelete,
  });
  final GirlCharacter character;
  final bool selected;
  final VoidCallback onUse;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final custom = character.avatarColor != null;
    return ListTile(
      selected: selected,
      leading: _CharacterAvatar(
        character: character,
        color: custom ? _parseColor(character.avatarColor) : null,
      ),
      title: Text(character.name),
      subtitle: character.description.isEmpty
          ? null
          : Text(
              character.description,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (onDelete != null)
            IconButton(
              tooltip: '删除角色 ${character.name}',
              onPressed: onDelete,
              icon: const Icon(Icons.delete_outline),
            ),
          TextButton(onPressed: onUse, child: const Text('使用')),
        ],
      ),
    );
  }
}

class _CharacterAvatar extends ConsumerWidget {
  const _CharacterAvatar({required this.character, this.color});
  final GirlCharacter character;
  final Color? color;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    const radius = 20.0;
    final name = character.name;
    final fallback = CircleAvatar(
      radius: radius,
      backgroundColor:
          color ?? Theme.of(context).colorScheme.secondaryContainer,
      child: Text(name.isEmpty ? '?' : name[0]),
    );
    // Custom characters carry their own colour; built-in ones render the SVG
    // served by the avatar endpoint.
    if (color != null) return fallback;
    return ref
        .watch(girlAvatarProvider(character.id))
        .maybeWhen(
          data: (svg) => SizedBox(
            width: radius * 2,
            height: radius * 2,
            child: ClipOval(
              child: SvgPicture.string(
                svg,
                fit: BoxFit.cover,
                placeholderBuilder: (_) => fallback,
                errorBuilder: (_, __, ___) => fallback,
              ),
            ),
          ),
          orElse: () => fallback,
        );
  }
}

Color _parseColor(String? value) {
  final hex = value?.replaceFirst('#', '');
  if (hex != null && hex.length == 6) {
    final parsed = int.tryParse(hex, radix: 16);
    if (parsed != null) return Color(0xFF000000 | parsed);
  }
  return Colors.indigo;
}

class _CreateCharacterDialog extends ConsumerStatefulWidget {
  const _CreateCharacterDialog();
  @override
  ConsumerState<_CreateCharacterDialog> createState() =>
      _CreateCharacterDialogState();
}

class _CreateCharacterDialogState
    extends ConsumerState<_CreateCharacterDialog> {
  final name = TextEditingController();
  final description = TextEditingController();
  final personality = TextEditingController();
  final speakingStyle = TextEditingController();
  final greeting = TextEditingController();
  bool busy = false;

  @override
  void dispose() {
    name.dispose();
    description.dispose();
    personality.dispose();
    speakingStyle.dispose();
    greeting.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (name.text.trim().isEmpty || busy) return;
    setState(() => busy = true);
    final ok = await ref
        .read(girlAiControllerProvider.notifier)
        .createCharacter({
          'name': name.text.trim(),
          if (description.text.trim().isNotEmpty)
            'description': description.text.trim(),
          if (personality.text.trim().isNotEmpty)
            'personality': personality.text.trim(),
          if (speakingStyle.text.trim().isNotEmpty)
            'speaking_style': speakingStyle.text.trim(),
          if (greeting.text.trim().isNotEmpty)
            'greetings': [greeting.text.trim()],
        });
    if (!mounted) return;
    if (ok) {
      Navigator.of(context).pop(true);
      return;
    }
    setState(() => busy = false);
    final message = ref.read(girlAiControllerProvider).error;
    if (message != null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('新建角色'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            key: const Key('characterName'),
            controller: name,
            decoration: const InputDecoration(labelText: '名称'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: description,
            decoration: const InputDecoration(labelText: '简介'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: personality,
            decoration: const InputDecoration(labelText: '性格'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: speakingStyle,
            decoration: const InputDecoration(labelText: '说话风格'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: greeting,
            decoration: const InputDecoration(labelText: '开场白'),
          ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: busy ? null : () => Navigator.of(context).pop(false),
        child: const Text('取消'),
      ),
      TextButton(onPressed: busy ? null : _submit, child: const Text('创建')),
    ],
  );
}

class _MemorySheet extends ConsumerStatefulWidget {
  const _MemorySheet();
  @override
  ConsumerState<_MemorySheet> createState() => _MemorySheetState();
}

class _MemorySheetState extends ConsumerState<_MemorySheet> {
  @override
  Widget build(BuildContext context) {
    final state = ref.watch(girlAiControllerProvider);
    final controller = ref.read(girlAiControllerProvider.notifier);
    return SafeArea(
      child: SizedBox(
        height: MediaQuery.sizeOf(context).height * 0.7,
        child: ListView(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 8, 0),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      '记忆库',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                  ),
                  IconButton(
                    tooltip: '关闭记忆库',
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
            ),
            const ListTile(dense: true, title: Text('已保存记忆')),
            if (state.memories.isEmpty)
              const _LibraryEmpty(
                icon: Icons.psychology_alt,
                title: '暂无已保存记忆',
                subtitle: '确认记忆候选后，它们会保存在这里',
                compact: true,
              ),
            for (final memory in state.memories)
              ListTile(
                dense: true,
                title: Text('${memory.key}: ${memory.value}'),
                subtitle: Text(memory.status),
                trailing: IconButton(
                  tooltip: '删除记忆 ${memory.key}',
                  onPressed: state.busyIds.contains(memory.id)
                      ? null
                      : () => controller.removeMemory(memory.id),
                  icon: const Icon(Icons.delete_outline),
                ),
              ),
            const Divider(height: 1),
            const ListTile(dense: true, title: Text('偏好')),
            if (state.preferences.isEmpty)
              const _LibraryEmpty(
                icon: Icons.tune,
                title: '暂无偏好',
                subtitle: '对话中确认的偏好会显示在这里',
                compact: true,
              ),
            for (final preference in state.preferences)
              ListTile(
                dense: true,
                title: Text('${preference.key}: ${preference.value}'),
                trailing: IconButton(
                  tooltip: '删除偏好 ${preference.key}',
                  onPressed: state.busyIds.contains(preference.id)
                      ? null
                      : () => controller.removePreference(preference.id),
                  icon: const Icon(Icons.delete_outline),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
