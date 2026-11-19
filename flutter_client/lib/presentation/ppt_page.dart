// ignore_for_file: curly_braces_in_flow_control_structures
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/auth_controller.dart';
import '../infrastructure/export/file_exporter.dart';
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
  String? activeAction;
  String? taskId;
  String? pptId;
  String? savedPath;
  String? pdfPath;
  String message = '';
  bool messageIsError = false;

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
      activeAction = null;
      taskId = null;
      pptId = null;
      savedPath = null;
      pdfPath = null;
      message = '';
      messageIsError = false;
    });
  }

  void _announce(String text, {bool error = false}) {
    if (!mounted) return;
    setState(() {
      message = text;
      messageIsError = error;
    });
  }

  Future<String?> _exportMobile(String path) async {
    final exporter = ref.read(fileExporterProvider);
    if (!exporter.isMobile) return null;
    return exporter.save(path);
  }

  static String _firstNonEmpty(List<Object?> values) {
    for (final value in values) {
      final text = value?.toString().trim() ?? '';
      if (text.isNotEmpty) return text;
    }
    return '';
  }

  static String _historyTime(Object? value) {
    final text = _firstNonEmpty([value]);
    if (text.isEmpty) return '时间未知';
    final parsed = DateTime.tryParse(text);
    if (parsed == null) return text;
    String two(int number) => number.toString().padLeft(2, '0');
    return '${parsed.year}-${two(parsed.month)}-${two(parsed.day)} '
        '${two(parsed.hour)}:${two(parsed.minute)}';
  }

  static String _historySubtitle(Map<String, dynamic> item) {
    final count = int.tryParse(
      _firstNonEmpty([item['slide_count'], item['slides_count']]),
    );
    final rawStatus = _firstNonEmpty([item['status']]);
    const statuses = {
      'completed': '已完成',
      'failed': '失败',
      'processing': '生成中',
      'pending': '等待中',
    };
    return [
      _historyTime(item['created_at'] ?? item['create_time']),
      count == null ? '页数未知' : '$count 页',
      if (rawStatus.isNotEmpty) statuses[rawStatus] ?? rawStatus,
    ].join(' · ');
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
      messageIsError = false;
    });
    try {
      final id = await client.generate(topic.text.trim());
      if (!mounted || run != generation) return;
      setState(() {
        taskId = id;
        message = '任务已提交，正在生成...';
        messageIsError = false;
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
        messageIsError = false;
      });
    } catch (error) {
      if (mounted && run == generation) {
        setState(() {
          busy = false;
          message = '任务失败：$error';
          messageIsError = true;
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
      activeAction = 'pptx';
      message = '下载中...';
      messageIsError = false;
    });
    try {
      final path = await PptClient(ref.read(authenticatedClientProvider))
          .download(id, (bytes) {
            if (mounted && run == generation) {
              setState(() => message = '下载中：$bytes bytes');
            }
          }, active: () => mounted && run == generation);
      if (!mounted || run != generation) return;
      String? target;
      try {
        target = await _exportMobile(path);
      } catch (error) {
        if (!mounted || run != generation) return;
        setState(() {
          busy = false;
          activeAction = null;
          savedPath = path;
          message = 'PPTX 已下载，但导出失败：$error\n$path';
          messageIsError = true;
        });
        return;
      }
      if (!mounted || run != generation) return;
      final text = target == null
          ? 'PPTX 已下载到应用私有目录，可用下方“导出到...”保存到手机：$path'
          : 'PPTX 已保存到：$target';
      setState(() {
        busy = false;
        activeAction = null;
        savedPath = path;
        message = text;
        messageIsError = false;
      });
    } catch (error) {
      if (!mounted || run != generation) return;
      final text = '下载失败：$error';
      setState(() {
        busy = false;
        activeAction = null;
        message = text;
        messageIsError = true;
      });
    }
  }

  Future<void> report() async {
    final id = taskId;
    if (id == null || busy) return;
    final run = generation;
    setState(() {
      busy = true;
      activeAction = 'report';
      message = '质量报告获取中...';
      messageIsError = false;
    });
    try {
      final value = await PptClient(
        ref.read(authenticatedClientProvider),
      ).qualityReport(id);
      if (!mounted || run != generation) return;
      setState(() {
        busy = false;
        activeAction = null;
        message = '质量报告已加载';
        messageIsError = false;
      });
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
      if (!mounted || run != generation) return;
      final text = '质量报告获取失败：$error';
      setState(() {
        busy = false;
        activeAction = null;
        message = text;
        messageIsError = true;
      });
    }
  }

  Future<void> history() async {
    if (busy) return;
    final run = generation;
    setState(() {
      busy = true;
      activeAction = 'history';
      message = '历史记录读取中...';
      messageIsError = false;
    });
    try {
      final items = await PptClient(
        ref.read(authenticatedClientProvider),
      ).history();
      if (!mounted || run != generation) return;
      setState(() {
        busy = false;
        activeAction = null;
        message = '历史记录已加载，选择一条继续操作';
      });
      showModalBottomSheet<void>(
        context: context,
        builder: (sheetContext) => ListView(
          children: [
            if (items.isEmpty)
              const ListTile(dense: true, title: Text('暂无历史记录')),
            for (final item in items)
              ListTile(
                title: Text(
                  _firstNonEmpty([item['title'], item['topic'], '未命名 PPT']),
                ),
                subtitle: Text(_historySubtitle(item)),
                trailing: const Icon(Icons.chevron_right),
                onTap: () {
                  final selectedPptId = _firstNonEmpty([
                    item['ppt_id'],
                    item['task_id'],
                    item['id'],
                  ]);
                  final selectedTaskId = _firstNonEmpty([
                    item['task_id'],
                    item['ppt_id'],
                    item['id'],
                  ]);
                  if (selectedPptId.isEmpty || selectedTaskId.isEmpty) {
                    _announce('这条历史缺少任务 ID，无法打开', error: true);
                    return;
                  }
                  Navigator.of(sheetContext).pop();
                  setState(() {
                    pptId = selectedPptId;
                    taskId = selectedTaskId;
                    savedPath = null;
                    pdfPath = null;
                    message = '已选择历史 PPT：$selectedPptId';
                    messageIsError = false;
                  });
                  _announce('已选择历史 PPT：$selectedPptId');
                },
              ),
          ],
        ),
      );
    } catch (e) {
      if (!mounted || run != generation) return;
      final text = '历史读取失败：$e';
      setState(() {
        busy = false;
        activeAction = null;
        message = text;
        messageIsError = true;
      });
    }
  }

  Future<void> downloadPdf() async {
    final id = pptId;
    if (id == null || busy) return;
    final run = generation;
    setState(() {
      busy = true;
      activeAction = 'pdf';
      message = 'PDF 下载中...';
      messageIsError = false;
    });
    try {
      final path = await PptClient(
        ref.read(authenticatedClientProvider),
      ).download(id, (_) {}, format: 'pdf');
      if (!mounted || run != generation) return;
      String? target;
      try {
        target = await _exportMobile(path);
      } catch (error) {
        if (!mounted || run != generation) return;
        setState(() {
          busy = false;
          activeAction = null;
          pdfPath = path;
          message = 'PDF 已下载，但导出失败：$error\n$path';
          messageIsError = true;
        });
        return;
      }
      if (!mounted || run != generation) return;
      final text = target == null
          ? 'PDF 已下载到应用私有目录，可用下方“导出到...”保存到手机：$path'
          : 'PDF 已保存到：$target';
      setState(() {
        busy = false;
        activeAction = null;
        pdfPath = path;
        message = text;
        messageIsError = false;
      });
    } catch (e) {
      if (!mounted || run != generation) return;
      final text = 'PDF 下载失败：$e';
      setState(() {
        busy = false;
        activeAction = null;
        message = text;
        messageIsError = true;
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
                                _announce('生成提交失败：$e', error: true);
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
      if (mounted && run == generation) _announce('大纲创建失败：$e', error: true);
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
            if (message.isNotEmpty)
              Container(
                margin: const EdgeInsets.only(bottom: 12),
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 10,
                ),
                decoration: BoxDecoration(
                  color: messageIsError
                      ? Theme.of(context).colorScheme.errorContainer
                      : Theme.of(context).colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      messageIsError ? Icons.error_outline : Icons.info_outline,
                      size: 18,
                    ),
                    const SizedBox(width: 8),
                    Expanded(child: Text(message)),
                  ],
                ),
              ),
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
                child: Text(activeAction == 'pptx' ? 'PPTX 下载中...' : '下载 PPTX'),
              ),
            if (pptId != null)
              OutlinedButton(
                onPressed: busy ? null : report,
                child: Text(activeAction == 'report' ? '质量报告获取中...' : '查看质量报告'),
              ),
            if (pptId != null)
              OutlinedButton(
                onPressed: busy ? null : downloadPdf,
                child: Text(activeAction == 'pdf' ? 'PDF 下载中...' : '下载 PDF'),
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
