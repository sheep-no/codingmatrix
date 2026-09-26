import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../infrastructure/export/file_exporter.dart';

/// Export action for a file already written to the app documents directory.
class SavedFileActions extends ConsumerStatefulWidget {
  const SavedFileActions({super.key, required this.path});
  final String path;
  @override
  ConsumerState<SavedFileActions> createState() => _SavedFileActionsState();
}

class _SavedFileActionsState extends ConsumerState<SavedFileActions> {
  bool busy = false;
  String? message;

  Future<void> _export() async {
    if (busy) return;
    setState(() {
      busy = true;
      message = null;
    });
    try {
      final target = await ref.read(fileExporterProvider).save(widget.path);
      if (!mounted) return;
      setState(() => message = target == null ? '已取消导出' : '已导出到：$target');
    } on FileExportException catch (e) {
      if (mounted) setState(() => message = e.message);
    } catch (e) {
      if (mounted) setState(() => message = '导出失败：$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      TextButton.icon(
        onPressed: busy ? null : _export,
        icon: const Icon(Icons.save_alt),
        label: Text(busy ? '导出中...' : '导出到...'),
      ),
      if (message != null) SelectableText(message!),
    ],
  );
}
