import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../../domain/models/workflow_models.dart';
import '../auth/authenticated_client.dart';

class WorkflowClient {
  WorkflowClient(this.api);
  final AuthenticatedClient api;
  Future<Stream<Map<String, dynamic>>> execute(
    String input,
    int timeout,
  ) async {
    if (input.trim().isEmpty || timeout < 60 || timeout > 3600) {
      throw StateError('输入无效');
    }
    final request = http.Request(
      'POST',
      Uri.parse(api.auth.baseUrl).resolve('/api/v1/workflow/execute'),
    );
    request.headers.addAll({
      'Content-Type': 'application/json',
      'Accept': 'application/x-ndjson',
    });
    request.body = jsonEncode({
      'natural_language_request': input.trim(),
      'timeout': timeout,
      'export_workflow': false,
    });
    final response = await api.send(request);
    return parse(response.stream);
  }

  static Stream<Map<String, dynamic>> parse(Stream<List<int>> bytes) {
    var buffer = '';
    // Transform subscriptions propagate cancellation even while the server is idle.
    return bytes
        .transform(utf8.decoder)
        .transform(
          StreamTransformer<String, Map<String, dynamic>>.fromHandlers(
            handleData: (text, sink) {
              try {
                buffer += text;
                var newline = buffer.indexOf('\n');
                while (newline >= 0) {
                  if (newline > 1024 * 1024) {
                    throw const FormatException('事件过大');
                  }
                  final line = buffer.substring(0, newline).trim();
                  buffer = buffer.substring(newline + 1);
                  if (line.isNotEmpty) sink.add(_event(line));
                  newline = buffer.indexOf('\n');
                }
                if (buffer.length > 1024 * 1024) {
                  throw const FormatException('事件过大');
                }
              } catch (error, stack) {
                buffer = '';
                sink.addError(error, stack);
              }
            },
            handleDone: (sink) {
              try {
                if (buffer.trim().isNotEmpty) sink.add(_event(buffer));
              } catch (error, stack) {
                sink.addError(error, stack);
              } finally {
                sink.close();
              }
            },
          ),
        );
  }

  static Map<String, dynamic> _event(String line) {
    final value = jsonDecode(line);
    if (value is! Map || value['event'] is! String) {
      throw const FormatException('事件格式无效');
    }
    return Map<String, dynamic>.from(value);
  }

  Future<WorkflowSnapshot> status(String id) async => WorkflowSnapshot.fromJson(
    Map<String, dynamic>.from(
      await api.requestJson(
            '/api/v1/workflow/status/${Uri.encodeComponent(id)}',
          )
          as Map,
    ),
  );

  Future<Map<String, dynamic>> importWorkflow(
    Map<String, dynamic> graph,
  ) async => Map<String, dynamic>.from(
    await api.requestJson(
          '/api/v1/workflow/import',
          method: 'POST',
          body: graph,
        )
        as Map,
  );
  Future<Map<String, dynamic>> exportWorkflow(String id) async =>
      Map<String, dynamic>.from(
        await api.requestJson(
              '/api/v1/workflow/export/${Uri.encodeComponent(id)}',
            )
            as Map,
      );
  Future<List<Map<String, dynamic>>> history() async => [
    for (final x
        in (await api.requestJson('/api/v1/workflow/history') as Map)['items']
                as List? ??
            const [])
      Map<String, dynamic>.from(x),
  ];
  Future<void> deleteHistory(String id) async => api.requestJson(
    '/api/v1/workflow/history/${Uri.encodeComponent(id)}',
    method: 'DELETE',
  );
}
