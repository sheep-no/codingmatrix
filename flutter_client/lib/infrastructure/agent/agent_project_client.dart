import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import '../auth/authenticated_client.dart';

class AgentProjectClient {
  AgentProjectClient(this.api, {Future<Directory> Function()? directory})
    : directory = directory ?? getApplicationDocumentsDirectory;

  final AuthenticatedClient api;
  final Future<Directory> Function() directory;

  Future<void> decide(String sessionId, Map<String, String> choices) async {
    final result = await api.requestJson(
      '/api/v1/agent/session/${Uri.encodeComponent(sessionId)}/decision',
      method: 'POST',
      body: choices,
    );
    if (result is! Map || result['status'] != 'submitted') {
      throw StateError('决策等待已结束，请查看任务进度');
    }
  }

  Future<List<String>> files(String project) async {
    final result = await api.requestJson(
      Uri(
        path: '/api/v1/agent/generate/files',
        queryParameters: {'project_path': project},
      ).toString(),
    );
    final entries = (result as Map)['files'] as List;
    return entries.map((entry) => (entry as Map)['path'] as String).toList()
      ..sort();
  }

  Future<String> read(String project, String path) async {
    final result = await api.requestJson(
      Uri(
        path: '/api/v1/agent/generate/read',
        queryParameters: {'project_path': project, 'file_path': path},
      ).toString(),
    );
    return (result as Map)['content'] as String;
  }

  Future<String> download(
    String project,
    void Function(int) progress, {
    bool Function()? active,
  }) async {
    final ref = api.auth.session?.accessTokenRef;
    final folder = await directory();
    final uri = Uri.parse(api.auth.baseUrl).resolve(
      '/api/v1/agent/generate/download/${project.split('/').map(Uri.encodeComponent).join('/')}',
    );
    final response = await api.send(http.Request('GET', uri));
    const limit = 200 * 1024 * 1024;
    if (response.statusCode != 200 || (response.contentLength ?? 0) > limit) {
      await response.stream.take(0).drain<void>();
      throw StateError('项目包不可下载或超过 200 MB');
    }
    final file = File(
      '${folder.path}/project-${DateTime.now().microsecondsSinceEpoch}.zip.part',
    );
    final sink = await file.open(mode: FileMode.write);
    var bytes = 0;
    var complete = false;
    final prefix = <int>[];
    try {
      await for (final chunk in response.stream) {
        if (active?.call() == false ||
            api.auth.session?.accessTokenRef != ref) {
          throw StateError('下载已取消');
        }
        bytes += chunk.length;
        if (bytes > limit) throw StateError('项目包超过 200 MB');
        prefix.addAll(chunk.take(4 - prefix.length));
        await sink.writeFrom(chunk);
        progress(bytes);
      }
      await sink.flush();
      if (bytes < 22 ||
          (response.contentLength != null && bytes != response.contentLength) ||
          prefix.length < 4 ||
          prefix[0] != 0x50 ||
          prefix[1] != 0x4b ||
          !((prefix[2] == 3 && prefix[3] == 4) ||
              (prefix[2] == 5 && prefix[3] == 6))) {
        throw StateError('项目包不完整');
      }
      if (active?.call() == false || api.auth.session?.accessTokenRef != ref) {
        throw StateError('下载已取消');
      }
      complete = true;
    } finally {
      await sink.close();
      if (!complete && await file.exists()) await file.delete();
    }
    if (active?.call() == false || api.auth.session?.accessTokenRef != ref) {
      throw StateError('下载已取消');
    }
    final saved = await file.rename(
      file.path.substring(0, file.path.length - 5),
    );
    return saved.path;
  }
}
