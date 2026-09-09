import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../application/workbench_controller.dart';

class AgentDecisionPage extends ConsumerStatefulWidget {
  const AgentDecisionPage({super.key});
  @override
  ConsumerState<AgentDecisionPage> createState() => _AgentDecisionPageState();
}

class _AgentDecisionPageState extends ConsumerState<AgentDecisionPage> {
  final choices = <String, String>{};

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(workbenchControllerProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('架构决策')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('服务端最多等待 120 秒，超时后会使用默认方案继续。'),
          if (state.decisions.isEmpty)
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('当前没有待提交的决策，请返回工作台查看进度。'),
            ),
          ...state.decisions.map(
            (question) => Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      question.question,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    Text(question.context),
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      key: ValueKey(
                        '${state.task?.sessionId}/${question.id}/${question.options}',
                      ),
                      isExpanded: true,
                      initialValue:
                          question.options.any(
                            (option) => option['label'] == choices[question.id],
                          )
                          ? choices[question.id]
                          : question.defaultChoice,
                      items: question.options
                          .map(
                            (option) => DropdownMenuItem(
                              value: option['label'],
                              child: Text(
                                option['label']!,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          )
                          .toList(),
                      onChanged: state.decisionBusy
                          ? null
                          : (value) => setState(() {
                              if (value != null) choices[question.id] = value;
                            }),
                    ),
                    ...question.options.map(
                      (option) => Text(
                        '${option['label']}：${option['description'] ?? ''}',
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          if (state.actionError != null)
            Text(
              state.actionError!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          if (state.decisions.isNotEmpty)
            FilledButton(
              onPressed: state.decisionBusy
                  ? null
                  : () => ref
                        .read(workbenchControllerProvider.notifier)
                        .submitDecisions({
                          for (final question in state.decisions)
                            question.id:
                                choices[question.id] ??
                                question.defaultChoice ??
                                '',
                        }),
              child: Text(state.decisionBusy ? '提交中…' : '提交决策'),
            ),
        ],
      ),
    );
  }
}
