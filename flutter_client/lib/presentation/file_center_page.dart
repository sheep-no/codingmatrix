import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import '../application/auth_controller.dart';
import 'shell_scaffold.dart';

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
      if (mounted && epoch == _epoch) setState(() => message = '上传完成');
    } catch (e) {
      if (mounted && epoch == _epoch) setState(() => message = '上传失败：$e');
    } finally {
      if (mounted && epoch == _epoch) setState(() => busy = false);
    }
  }

  void _resetAccount() {
    _epoch++;
    setState(() {
      files.clear();
      message = null;
      busy = false;
    });
  }

  // FileUploadResponse exposes `filename`; resumable/legacy payloads may use `name`.
  String _displayName(Map<String, dynamic> file, String id) =>
      '${file['name'] ?? file['filename'] ?? 'file-$id'}';

  Future<void> download(Map<String, dynamic> file) async {
    final id = '${file['file_id'] ?? file['id'] ?? ''}';
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
      final folder = await getApplicationDocumentsDirectory();
      final name = _displayName(
        file,
        id,
      ).replaceAll(RegExp(r'[^A-Za-z0-9._-]'), '_');
      final output = File('${folder.path}/$name');
      await output.writeAsBytes(await response.stream.toBytes(), flush: true);
      if (mounted && epoch == _epoch) {
        setState(() => message = '已保存到：${output.path}');
      }
    } catch (e) {
      if (mounted && epoch == _epoch) setState(() => message = '下载失败：$e');
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
          for (final file in files)
            ListTile(
              title: Text('${file['name'] ?? file['filename'] ?? '文件'}'),
              subtitle: Text(
                '${file['file_id'] ?? file['id'] ?? ''}\n'
                '${file['file_path'] ?? file['server_path'] ?? file['download_url'] ?? ''}',
              ),
              isThreeLine: true,
              trailing: IconButton(
                onPressed: busy ? null : () => download(file),
                icon: const Icon(Icons.download),
              ),
            ),
        ],
      ),
    );
  }
}
