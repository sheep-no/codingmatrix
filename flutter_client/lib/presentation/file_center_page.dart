import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import '../application/auth_controller.dart';
import '../infrastructure/share/file_sharer.dart';
import 'shell_scaffold.dart';

typedef DownloadWriter =
    Future<String> Function(http.StreamedResponse response, String name);

Future<String> _writeDownload(
  http.StreamedResponse response,
  String name,
) async {
  final folder = await getTemporaryDirectory();
  final output = File('${folder.path}/$name');
  await output.writeAsBytes(await response.stream.toBytes(), flush: true);
  return output.path;
}

final fileDownloadWriterProvider = Provider<DownloadWriter>(
  (ref) => _writeDownload,
);

class FileCenterPage extends ConsumerStatefulWidget {
  const FileCenterPage({super.key});
  @override
  ConsumerState<FileCenterPage> createState() => _FileCenterPageState();
}

class _FileCenterPageState extends ConsumerState<FileCenterPage> {
  bool busy = false;
  String? message;
  final files = <Map<String, dynamic>>[];
  // Bumped on account change so a late upload/download result cannot land in
  // the next account's page state.
  int _epoch = 0;
  Future<void> upload() async {
    // Hold busy across the picker too, otherwise a second tap opens another
    // picker while the first is still open.
    if (busy) return;
    final epoch = _epoch;
    setState(() {
      busy = true;
      message = null;
    });
    FilePickerResult? picked;
    try {
      picked = await FilePicker.platform.pickFiles(allowMultiple: true);
    } catch (e) {
      if (mounted && epoch == _epoch) {
        setState(() {
          busy = false;
          message = '选择文件失败：$e';
        });
      }
      return;
    }
    if (picked == null) {
      if (mounted && epoch == _epoch) setState(() => busy = false);
      return;
    }
    if (!mounted || epoch != _epoch) return;
    try {
      for (final file in picked.files) {
        if (file.path == null) continue;
        final api = ref.read(authenticatedClientProvider);
        final result = file.size > 10 * 1024 * 1024
            ? await api.uploadFileResumable(file.path!)
            : await api.uploadFile(file.path!);
        if (!mounted || epoch != _epoch) return;
        setState(() => files.add(result));
      }
      if (mounted && epoch == _epoch) {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(
            const SnackBar(
              content: Text('上传完成'),
              duration: Duration(seconds: 2),
            ),
          );
      }
    } catch (e) {
      if (mounted && epoch == _epoch) setState(() => message = '上传失败：$e');
    } finally {
      if (mounted && epoch == _epoch) setState(() => busy = false);
    }
  }

  void _resetAccount() {
    _epoch++;
    ScaffoldMessenger.maybeOf(context)?.clearSnackBars();
    setState(() {
      files.clear();
      message = null;
      busy = false;
    });
  }

  String _fileId(Map<String, dynamic> file) =>
      '${file['file_id'] ?? file['id'] ?? ''}';

  // FileUploadResponse exposes `filename`; resumable/legacy payloads may use `name`.
  String _displayName(Map<String, dynamic> file, String id) =>
      '${file['name'] ?? file['filename'] ?? 'file-$id'}';

  String _safeName(String name) {
    final safe = name.replaceAll(RegExp(r'[\\/:*?"<>|]'), '_').trim();
    return safe.isEmpty ? 'download' : safe;
  }

  String _formatSize(Object? value) {
    final bytes = value is num ? value.toInt() : int.tryParse('${value ?? ''}');
    if (bytes == null || bytes < 0) return '大小未知';
    if (bytes < 1024) return '$bytes B';
    const units = ['KB', 'MB', 'GB', 'TB'];
    var size = bytes / 1024;
    var unit = 0;
    while (size >= 1024 && unit < units.length - 1) {
      size /= 1024;
      unit++;
    }
    final text = size >= 10 ? size.toStringAsFixed(0) : size.toStringAsFixed(1);
    return '$text ${units[unit]}';
  }

  String _formatTime(Object? value) {
    final raw = '${value ?? ''}';
    final parsed = DateTime.tryParse(raw);
    if (parsed == null) return raw.isEmpty ? '时间未知' : raw;
    final time = parsed.isUtc ? parsed.toLocal() : parsed;
    String two(int part) => part.toString().padLeft(2, '0');
    return '${time.year}-${two(time.month)}-${two(time.day)} '
        '${two(time.hour)}:${two(time.minute)}';
  }

  Future<void> download(Map<String, dynamic> file) async {
    final id = _fileId(file);
    if (id.isEmpty || busy) return;
    final epoch = _epoch;
    setState(() {
      busy = true;
      message = '下载中...';
    });
    try {
      final api = ref.read(authenticatedClientProvider);
      final response = await api.send(
        http.Request(
          'GET',
          Uri.parse(api.auth.baseUrl).resolve('/api/v1/files/$id/download'),
        ),
      );
      if (response.statusCode != 200) throw StateError('文件下载失败');
      final name = _safeName(_displayName(file, id));
      final path = await ref.read(fileDownloadWriterProvider)(response, name);
      await ref.read(fileSharerProvider).share(path, subject: name);
      if (mounted && epoch == _epoch) {
        setState(() => message = null);
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(
            const SnackBar(
              content: Text('下载完成，请选择要使用的应用'),
              duration: Duration(seconds: 2),
            ),
          );
      }
    } catch (e) {
      if (mounted && epoch == _epoch) {
        setState(
          () => message = e is FileShareException
              ? '下载完成，但无法打开分享：${e.message}'
              : '下载失败：$e',
        );
      }
    } finally {
      if (mounted && epoch == _epoch) setState(() => busy = false);
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
      title: '文件中心',
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          FilledButton.icon(
            onPressed: busy ? null : upload,
            icon: const Icon(Icons.upload_file),
            label: Text(busy ? '上传中...' : '选择文件上传'),
          ),
          if (message != null) Text(message!),
          const Divider(),
          if (files.isEmpty) const ListTile(dense: true, title: Text('尚未上传文件')),
          for (final file in files)
            ListTile(
              title: Text(
                _displayName(file, _fileId(file)),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              subtitle: Text(
                '${_formatSize(file['file_size'])} · '
                '${_formatTime(file['created_at'])}',
              ),
              trailing: IconButton(
                tooltip: '下载并分享',
                onPressed: busy ? null : () => download(file),
                icon: const Icon(Icons.download),
              ),
            ),
        ],
      ),
    );
  }
}
