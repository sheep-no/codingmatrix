import '../auth/authenticated_client.dart';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

class PptClient {
  PptClient(this.api);
  final AuthenticatedClient api;

  Future<String> generate(String topic) async {
    final result = await api.requestJson(
      '/api/v1/pptx/generate_task',
      method: 'POST',
      body: {'topic': topic, 'output_format': 'pptx'},
    );
    final map = Map<String, dynamic>.from(result as Map);
    return (map['task_id'] ?? map['id'] ?? '').toString();
  }

  Future<Map<String, dynamic>> task(String taskId) async {
    final result = await api.requestJson(
      '/api/v1/tasks/${Uri.encodeComponent(taskId)}',
    );
    return Map<String, dynamic>.from(result as Map);
  }

  Future<Map<String, dynamic>> waitForCompletion(
    String taskId, {
    bool Function()? active,
  }) async {
    while (active?.call() != false) {
      final value = await task(taskId);
      final status = value['status']?.toString().toLowerCase();
      if (status == 'completed' ||
          status == 'success' ||
          status == 'failed' ||
          status == 'error' ||
          status == 'cancelled') {
        return value;
      }
      await Future<void>.delayed(const Duration(seconds: 2));
    }
    throw StateError('任务查询已取消');
  }

  Future<String> download(
    String pptId,
    void Function(int) progress, {
    bool Function()? active,
    String format = 'pptx',
  }) {
    return _download(pptId, progress, active: active, format: format);
  }

  Future<String> _download(
    String pptId,
    void Function(int) progress, {
    bool Function()? active,
    String format = 'pptx',
  }) async {
    final ref = api.auth.session?.accessTokenRef;
    final response = await api.send(
      http.Request(
        'GET',
        Uri.parse(api.auth.baseUrl).resolve(
          '/api/v1/pptx/download/${Uri.encodeComponent(pptId)}?format=$format',
        ),
      ),
    );
    const limit = 200 * 1024 * 1024;
    if (response.statusCode != 200 || (response.contentLength ?? 0) > limit) {
      await response.stream.drain<void>();
      throw StateError('PPTX 不可下载或超过 200 MB');
    }
    final folder = await getApplicationDocumentsDirectory();
    final file = File('${folder.path}/ppt-$pptId.pptx.part');
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
        if (bytes > limit) {
          throw StateError('PPTX 超过 200 MB');
        }
        prefix.addAll(chunk.take(4 - prefix.length));
        await sink.writeFrom(chunk);
        progress(bytes);
      }
      await sink.flush();
      if (format == 'pptx' &&
          (bytes < 4 || prefix[0] != 0x50 || prefix[1] != 0x4b)) {
        throw StateError('PPTX 不完整');
      }
      complete = true;
    } finally {
      await sink.close();
      if (!complete && await file.exists()) await file.delete();
    }
    return (await file.rename(
      file.path
          .substring(0, file.path.length - 5)
          .replaceFirst('.pptx', '.$format'),
    )).path;
  }

  Future<Map<String, dynamic>> qualityReport(String taskId) async {
    final result = await api.requestJson('/api/v1/pptx/$taskId/quality-report');
    return Map<String, dynamic>.from(result as Map);
  }

  Future<List<Map<String, dynamic>>> history() async {
    final value = await api.requestJson('/api/v1/pptx/history');
    final list = value is Map ? value['items'] ?? value['history'] : value;
    return [
      for (final item in (list as List? ?? const []))
        Map<String, dynamic>.from(item),
    ];
  }

  Future<Map<String, dynamic>> createOutline(String prompt) async =>
      Map<String, dynamic>.from(
        await api.requestJson(
              '/api/v1/pptx/outlines',
              method: 'POST',
              body: {'prompt': prompt},
            )
            as Map,
      );
  Future<Map<String, dynamic>> approveOutline(String id) async =>
      Map<String, dynamic>.from(
        await api.requestJson(
              '/api/v1/pptx/outlines/${Uri.encodeComponent(id)}/approve',
              method: 'POST',
            )
            as Map,
      );
  Future<Map<String, dynamic>> generateFromOutline(String id) async =>
      Map<String, dynamic>.from(
        await api.requestJson(
              '/api/v1/pptx/outlines/${Uri.encodeComponent(id)}/generate',
              method: 'POST',
              body: {'quality_mode': 'standard'},
            )
            as Map,
      );

  Future<void> deleteHistory(String id) async => api.requestJson(
    '/api/v1/pptx/history/${Uri.encodeComponent(id)}',
    method: 'DELETE',
  );

  String downloadUrl(String pptId) => Uri.parse(api.auth.baseUrl)
      .resolve(
        '/api/v1/pptx/download/${Uri.encodeComponent(pptId)}?format=pptx',
      )
      .toString();

  String previewUrl(String pptId) => Uri.parse(api.auth.baseUrl)
      .resolve('/api/v1/pptx/preview/${Uri.encodeComponent(pptId)}?format=pptx')
      .toString();
}
