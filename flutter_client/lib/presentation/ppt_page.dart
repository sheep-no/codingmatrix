// ignore_for_file: curly_braces_in_flow_control_structures
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/auth_controller.dart';
import '../infrastructure/ppt/ppt_client.dart';
import 'account_overlays.dart';
import 'saved_file_actions.dart';
import 'shell_scaffold.dart';

class PptPage extends ConsumerStatefulWidget {
  const PptPage({super.key});
  @override
  ConsumerState<PptPage> createState() => _PptPageState();
}

class _PptPageState extends ConsumerState<PptPage> {
  final topic = TextEditingController();
  int generation = 0;
  bool busy = false;
  String? taskId;
  String? pptId;
  String? savedPath;
  String? pdfPath;
  String message = '';

  @override
  void dispose() {
    generation++;
    topic.dispose();
    super.dispose();
  }

  void _resetAccount() {
    // Drop any in-flight generation so its late result cannot land in the
    // next account's state.
    generation++;
    closeAccountOverlays(context);
    topic.clear();
    setState(() {
      busy = false;
      taskId = null;
      pptId = null;
      savedPath = null;
      pdfPath = null;
      message = '';
    });
  }

  Future<void> generate() async {
    if (busy || topic.text.trim().isEmpty) return;
    final run = ++generation;
    final client = PptClient(ref.read(authenticatedClientProvider));
    setState(() {
      busy = true;
      taskId = null;
      pptId = null;
      message = '正在提交...';
    });
    try {
      final id = await client.generate(topic.text.trim());
      if (!mounted || run != generation) return;
      setState(() {
        taskId = id;
        message = '任务已提交，正在生成...';
      });
      final status = await client.waitForCompletion(
        id,
        active: () => mounted && run == generation,
      );
      if (!mounted || run != generation) return;
      final result = status['result'];
      final output = result is Map ? result['ppt_id'] : null;
      if (output == null || output.toString().isEmpty) {
        throw StateError('任务完成但未返回 ppt_id');
      }
      setState(() {
        pptId = output.toString();
        busy = false;
        message = '生成完成，可以下载';
      });
    } catch (error) {
      if (mounted && run == generation) {
        setState(() {
          busy = false;
          message = '任务失败：$error';
        });
      }
    }
  }

  Future<void> download() async {
    final id = pptId;
    if (id == null || busy) return;
    final run = generation;
    setState(() {
      busy = true;
      message = '下载中...';
    });
    try {
      final path = await PptClient(ref.read(authenticatedClientProvider))
          .download(id, (bytes) {
            if (mounted && run == generation) {
              setState(() => message = '下载中：$bytes bytes');
            }
          }, active: () => mounted && run == generation);
      if (mounted && run == generation) {
        setState(() {
          busy = false;
          savedPath = path;
          message = '已保存到：$path';
        });
      }
    } catch (error) {
      if (mounted && run == generation) {
        setState(() {
          busy = false;
          message = '下载失败：$error';
        });
      }
    }
  }

  Future<void> report() async {
    final id = taskId;
    if (id == null || busy) return;
    final run = generation;
    setState(() => busy = true);
    try {
      final value = await PptClient(
        ref.read(authenticatedClientProvider),
      ).qualityReport(id);
      if (!mounted || run != generation) return;
      showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('质量报告'),
          content: SingleChildScrollView(
            child: Text(
              value.entries.map((e) => '${e.key}: ${e.value}').join('\n'),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('关闭'),
            ),
          ],
        ),
      );
    } catch (error) {
      if (mounted && run == generation)
        setState(() => message = '质量报告获取失败：$error');
    } finally {
      if (mounted && run == generation) setState(() => busy = false);
    }
  }

  Future<void> history() async {
    if (busy) return;
    final run = generation;
    setState(() => busy = true);
    try {
      final items = await PptClient(
        ref.read(authenticatedClientProvider),
      ).history();
      if (!mounted || run != generation) return;
      showModalBottomSheet<void>(
        context: context,
        builder: (sheetContext) => ListView(
          children: [
            if (items.isEmpty)
              const ListTile(dense: true, title: Text('暂无历史记录')),
            for (final item in items)
              ListTile(
                title: Text('${item['topic'] ?? item['title'] ?? 'PPT'}'),
                subtitle: Text(
                  '${item['status'] ?? ''} · ${item['ppt_id'] ?? item['task_id'] ?? item['id'] ?? ''}',
                ),
                trailing: const Icon(Icons.chevron_right),
                onTap: () {
                  final id = '${item['id'] ?? ''}';
                  final selectedPptId =
                      '${item['ppt_id'] ?? item['task_id'] ?? id}';
                  final selectedTaskId =
                      '${item['task_id'] ?? item['ppt_id'] ?? id}';
                  if (selectedPptId.isEmpty) return;
                  Navigator.of(sheetContext).pop();
                  setState(() {
                    pptId = selectedPptId;
                    taskId = selectedTaskId.isEmpty ? null : selectedTaskId;
                    savedPath = null;
                    pdfPath = null;
                    message = '已选择历史 PPT：$selectedPptId';
                  });
                },
              ),
          ],
        ),
      );
    } catch (e) {
      if (mounted && run == generation) setState(() => message = '历史读取失败：$e');
    } finally {
      if (mounted && run == generation) setState(() => busy = false);
    }
  }

  Future<void> downloadPdf() async {
    final id = pptId;
    if (id == null || busy) return;
    final run = generation;
    setState(() {
      busy = true;
      message = 'PDF 下载中...';
    });
    try {
      final path = await PptClient(
        ref.read(authenticatedClientProvider),
      ).download(id, (_) {}, format: 'pdf');
      if (mounted && run == generation)
        setState(() {
          busy = false;
          pdfPath = path;
          message = 'PDF 已保存到：$path';
        });
    } catch (e) {
      if (mounted && run == generation)
        setState(() {
          busy = false;
          message = 'PDF 下载失败：$e';
        });
    }
  }

  Future<void> createOutline() async {
    if (topic.text.trim().isEmpty || busy) return;
    final run = generation;
    setState(() => busy = true);
    try {
      final result = await PptClient(
        ref.read(authenticatedClientProvider),
      ).createOutline(topic.text.trim());
      if (!mounted || run != generation) return;
      final id = '${result['outline_id'] ?? result['id'] ?? ''}';
      showDialog<void>(
        context: context,
        builder: (dialogContext) {
          var submitting = false;
          return StatefulBuilder(
            builder: (context, setDialogState) => AlertDialog(
              title: const Text('PPT 大纲'),
              content: SizedBox(
                width: double.maxFinite,
                height: MediaQuery.sizeOf(context).height * 0.55,
                child: _OutlinePreview(outline: result),
              ),
              actions: [
                TextButton(
                  onPressed: submitting
                      ? null
                      : () => Navigator.pop(dialogContext),
                  child: const Text('关闭'),
                ),
                if (id.isNotEmpty)
                  FilledButton(
                    onPressed: submitting
                        ? null
                        : () async {
                            setDialogState(() => submitting = true);
                            final client = PptClient(
                              ref.read(authenticatedClientProvider),
                            );
                            try {
                              await client.approveOutline(id);
                              final generated = await client
                                  .generateFromOutline(id);
                              if (mounted && run == generation)
                                setState(
                                  () => message =
                                      '已按大纲提交生成：${generated['task_id'] ?? generated['id'] ?? ''}',
                                );
                              if (dialogContext.mounted)
                                Navigator.pop(dialogContext);
                            } catch (e) {
                              if (mounted && run == generation)
                                setState(() => message = '生成提交失败：$e');
                              if (dialogContext.mounted)
                                Navigator.pop(dialogContext);
                            }
                          },
                    child: const Text('批准并生成'),
                  ),
              ],
            ),
          );
        },
      );
    } catch (e) {
      if (mounted && run == generation) setState(() => message = '大纲创建失败：$e');
    } finally {
      if (mounted && run == generation) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(
      authControllerProvider.select((s) => s.session?.accessTokenRef),
      (_, __) => _resetAccount(),
    );
    ref.listen(apiBaseUrlProvider, (_, __) => _resetAccount());
    return ShellScaffold(
      title: 'PPT 生成',
      actions: [
        IconButton(
          onPressed: busy ? null : history,
          icon: const Icon(Icons.history),
        ),
      ],
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: topic,
              minLines: 5,
              maxLines: 10,
              decoration: const InputDecoration(labelText: 'PPT 主题与内容要求'),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: busy ? null : generate,
              child: Text(busy ? '处理中...' : '生成 PPT'),
            ),
            OutlinedButton(
              onPressed: busy ? null : createOutline,
              child: const Text('先生成 PPT 大纲'),
            ),
            if (pptId != null)
              OutlinedButton(
                onPressed: busy ? null : download,
                child: const Text('下载 PPTX'),
              ),
            if (pptId != null)
              OutlinedButton(
                onPressed: busy ? null : report,
                child: const Text('查看质量报告'),
              ),
            if (pptId != null)
              OutlinedButton(
                onPressed: busy ? null : downloadPdf,
                child: const Text('下载 PDF'),
              ),
            if (message.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 16),
                child: Text(message),
              ),
            if (savedPath != null) SavedFileActions(path: savedPath!),
            if (pdfPath != null) SavedFileActions(path: pdfPath!),
          ],
        ),
      ),
    );
  }
}

class _OutlinePreview extends StatelessWidget {
  const _OutlinePreview({required this.outline});

  final Map<String, dynamic> outline;

  @override
  Widget build(BuildContext context) {
    final rawSlides = outline['slides'];
    final slides = rawSlides is List ? rawSlides : const <dynamic>[];
    final title = _text(outline['title']);
    final chips = <Widget>[
      _InfoChip(label: '${slides.length} 页'),
      if (_text(outline['scenario']).isNotEmpty)
        _InfoChip(label: _scenarioLabel(_text(outline['scenario']))),
      if (_text(outline['template_id']).isNotEmpty)
        _InfoChip(label: '模板 ${_text(outline['template_id'])}'),
      if (_text(outline['status']).isNotEmpty)
        _InfoChip(label: _statusLabel(_text(outline['status']))),
    ];

    return ListView(
      children: [
        if (title.isNotEmpty) ...[
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
        ],
        Wrap(spacing: 8, runSpacing: 8, children: chips),
        const SizedBox(height: 16),
        if (slides.isEmpty)
          const Text('大纲未返回幻灯片内容')
        else
          for (var index = 0; index < slides.length; index++)
            _OutlineSlideCard(index: index, slide: slides[index]),
      ],
    );
  }

  static String _scenarioLabel(String value) {
    const labels = {
      'business': '商业',
      'data_report': '数据报告',
      'product_pitch': '产品路演',
      'academic': '学术',
      'education': '教育',
      'general': '通用',
    };
    return labels[value] ?? value;
  }

  static String _statusLabel(String value) {
    const labels = {'draft': '草稿', 'approved': '已批准'};
    return labels[value] ?? value;
  }
}

class _OutlineSlideCard extends StatelessWidget {
  const _OutlineSlideCard({required this.index, required this.slide});

  final int index;
  final dynamic slide;

  @override
  Widget build(BuildContext context) {
    if (slide is! Map) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Text('${index + 1}. ${_text(slide)}'),
      );
    }

    final data = Map<String, dynamic>.from(slide as Map);
    final title = _text(data['title']);
    final keyMessage = _text(data['key_message']);
    final slideType = _text(data['slide_type']);
    final blocks = data['content_blocks'] is List
        ? data['content_blocks'] as List
        : const <dynamic>[];
    final asset = data['asset_intent'];
    final assetDescription = asset is Map ? _text(asset['description']) : '';
    final notes = _text(data['speaker_notes']);

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                CircleAvatar(
                  radius: 12,
                  child: Text(
                    '${index + 1}',
                    style: const TextStyle(fontSize: 12),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    title.isEmpty ? '第 ${index + 1} 页' : title,
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                ),
                if (slideType.isNotEmpty) const SizedBox(width: 8),
                if (slideType.isNotEmpty) _InfoChip(label: slideType),
              ],
            ),
            if (keyMessage.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(keyMessage),
            ],
            for (final block in blocks)
              if (block is Map && _text(block['content']).isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('• '),
                      Expanded(child: Text(_text(block['content']))),
                    ],
                  ),
                ),
            if (assetDescription.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                '配图：$assetDescription',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
            if (notes.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                '演讲备注：$notes',
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _InfoChip extends StatelessWidget {
  const _InfoChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 140),
          child: Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.labelSmall,
          ),
        ),
      ),
    );
  }
}

String _text(dynamic value) => value == null ? '' : value.toString().trim();
