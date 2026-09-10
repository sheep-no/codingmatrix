import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/girl_ai_controller.dart';

class VirtualGirlPage extends ConsumerStatefulWidget {
  const VirtualGirlPage({super.key});
  @override
  ConsumerState<VirtualGirlPage> createState() => _VirtualGirlPageState();
}

class _VirtualGirlPageState extends ConsumerState<VirtualGirlPage> {
  final input = TextEditingController();
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
    if (value.isEmpty) return;
    input.clear();
    ref.read(girlAiControllerProvider.notifier).send(value);
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(girlAiControllerProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('虚拟姬'),
        actions: [
          IconButton(
            tooltip: '历史记录',
            onPressed: () async {
              await ref.read(girlAiControllerProvider.notifier).loadHistory();
              if (!context.mounted) return;
              showModalBottomSheet<void>(
                context: context,
                builder: (_) => _HistorySheet(
                  records: ref.read(girlAiControllerProvider).history,
                ),
              );
            },
            icon: const Icon(Icons.history),
          ),
        ],
      ),
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
                child: Row(
                  children: [
                    if (state.emotion != null)
                      Chip(label: Text('情绪: ${state.emotion!.label}')),
                    const SizedBox(width: 8),
                    if (state.intent != null)
                      Chip(label: Text('意图: ${state.intent!.label}')),
                  ],
                ),
              ),
            Expanded(
              child: state.loading && state.messages.isEmpty
                  ? const Center(child: CircularProgressIndicator())
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
            if (state.error != null)
              Padding(
                padding: const EdgeInsets.all(8),
                child: Text(
                  state.error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
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
                        onPressed: () => ref
                            .read(girlAiControllerProvider.notifier)
                            .confirmMemory(memory),
                        icon: const Icon(Icons.check),
                      ),
                      IconButton(
                        tooltip: '忽略',
                        onPressed: () => ref
                            .read(girlAiControllerProvider.notifier)
                            .deleteMemory(memory),
                        icon: const Icon(Icons.close),
                      ),
                    ],
                  ),
                ),
              ),
            Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
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

class _HistorySheet extends StatelessWidget {
  const _HistorySheet({required this.records});
  final List records;

  @override
  Widget build(BuildContext context) => SafeArea(
    child: SizedBox(
      height: 420,
      child: records.isEmpty
          ? const Center(child: Text('暂无历史记录'))
          : ListView.builder(
              itemCount: records.length,
              itemBuilder: (_, index) {
                final item = records[index];
                return ListTile(
                  title: Text(item.content),
                  subtitle: Text(item.role),
                );
              },
            ),
    ),
  );
}
