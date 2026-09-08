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

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('PPT 生成')),
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
          if (pptId != null)
            OutlinedButton(
              onPressed: busy ? null : download,
              child: const Text('下载 PPTX'),
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
