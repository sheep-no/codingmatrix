// ignore_for_file: curly_braces_in_flow_control_structures
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/auth_controller.dart';
import '../infrastructure/ppt/ppt_client.dart';

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
  String message = '';

  @override
  void dispose() {
    generation++;
    topic.dispose();
    super.dispose();
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
    try {
      final value = await PptClient(
        ref.read(authenticatedClientProvider),
      ).qualityReport(id);
      if (!mounted) return;
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
      if (mounted) setState(() => message = '质量报告获取失败：$error');
    }
  }

  Future<void> history() async {
    try {
      final items = await PptClient(
        ref.read(authenticatedClientProvider),
      ).history();
      if (!mounted) return;
      showModalBottomSheet<void>(
        context: context,
        builder: (_) => ListView(
          children: [
            for (final item in items)
              ListTile(
                title: Text('${item['topic'] ?? item['title'] ?? 'PPT'}'),
                subtitle: Text(
                  '${item['status'] ?? ''} · ${item['ppt_id'] ?? item['id'] ?? ''}',
                ),
              ),
          ],
        ),
      );
    } catch (e) {
      if (mounted) setState(() => message = '历史读取失败：$e');
    }
  }

  Future<void> downloadPdf() async {
    final id = pptId;
    if (id == null || busy) return;
    setState(() {
      busy = true;
      message = 'PDF 下载中...';
    });
    try {
      final path = await PptClient(
        ref.read(authenticatedClientProvider),
      ).download(id, (_) {}, format: 'pdf');
      if (mounted)
        setState(() {
          busy = false;
          message = 'PDF 已保存到：$path';
        });
    } catch (e) {
      if (mounted)
        setState(() {
          busy = false;
          message = 'PDF 下载失败：$e';
        });
    }
  }

  Future<void> createOutline() async {
    if (topic.text.trim().isEmpty || busy) return;
    setState(() => busy = true);
    try {
      final result = await PptClient(
        ref.read(authenticatedClientProvider),
      ).createOutline(topic.text.trim());
      if (!mounted) return;
      final id = '${result['outline_id'] ?? result['id'] ?? ''}';
      showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('PPT 大纲'),
          content: SingleChildScrollView(child: Text(result.toString())),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('关闭'),
            ),
            if (id.isNotEmpty)
              FilledButton(
                onPressed: () async {
                  final client = PptClient(
                    ref.read(authenticatedClientProvider),
                  );
                  await client.approveOutline(id);
                  final generated = await client.generateFromOutline(id);
                  // The dialog remains mounted while the approval request is running.
                  // ignore: use_build_context_synchronously
                  if (context.mounted) {
                    Navigator.pop(dialogContext);
                    setState(
                      () => message =
                          '已按大纲提交生成：${generated['task_id'] ?? generated['id'] ?? ''}',
                    );
                  }
                },
                child: const Text('批准并生成'),
              ),
          ],
        ),
      );
    } catch (e) {
      if (mounted) setState(() => message = '大纲创建失败：$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('PPT 生成'),
      actions: [
        IconButton(
          onPressed: busy ? null : history,
          icon: const Icon(Icons.history),
        ),
      ],
    ),
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
        ],
      ),
    ),
  );
}
