import 'dart:convert';

import 'package:http/http.dart' as http;

import '../auth/credential_store.dart';

class AgentStreamException implements Exception {
  AgentStreamException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

/// Opens the authenticated Agent orchestration SSE stream.
class AgentStreamClient {
  AgentStreamClient({
    required this.baseUrl,
    required this.httpClient,
    required this.credentialStore,
    this.streamPath = '/api/v1/agent/orchestrate/stream',
  });

  final String baseUrl;
  final http.Client httpClient;
  final CredentialStore credentialStore;
  final String streamPath;

  Stream<String> generate({
    required String accessTokenRef,
    required String requirement,
    String? projectName,
    String? sessionId,
    bool isResume = false,
    bool enableReview = true,
    bool enableValidation = true,
    bool enableErrorRecovery = true,
    bool enableMemory = true,
    bool specFirst = true,
    bool dependencyGraph = true,
    bool incremental = false,
    String? apiKeyToken,
    String? providerId,
  }) async* {
    final token = credentialStore.read(accessTokenRef);
    if (token == null || token.isEmpty) {
      throw AgentStreamException('登录凭据已失效，请重新登录');
    }

    final request = http.Request('POST', _join(streamPath))
      ..headers['Authorization'] = 'Bearer $token'
      ..headers['Accept'] = 'text/event-stream'
      ..headers['Cache-Control'] = 'no-cache'
      ..headers['Content-Type'] = 'application/json'
      ..body = jsonEncode(<String, dynamic>{
        'requirement': requirement,
        'project_name': projectName,
        'session_id': sessionId,
        'is_resume': isResume,
        'enable_review': enableReview,
        'enable_validation': enableValidation,
        'enable_error_recovery': enableErrorRecovery,
        'enable_memory': enableMemory,
        'spec_first': specFirst,
        'dependency_graph': dependencyGraph,
        'incremental': incremental,
        if (apiKeyToken != null) 'api_key_token': apiKeyToken,
        if (providerId != null) 'provider_id': providerId,
      });

    final response = await httpClient.send(request);
    if (response.statusCode != 200) {
      await response.stream.drain<void>();
      throw AgentStreamException(
        'Agent 请求失败（HTTP ${response.statusCode}），请确认任务状态后手动恢复',
        statusCode: response.statusCode,
      );
    }

    yield* response.stream.transform(utf8.decoder);
  }

  Future<void> stop({
    required String accessTokenRef,
    required String sessionId,
  }) async {
    final token = credentialStore.read(accessTokenRef);
    if (token == null || token.isEmpty) {
      throw AgentStreamException('登录凭据已失效，请重新登录');
    }

    final response = await httpClient.post(
      _join('/api/v1/agent/stop/$sessionId'),
      headers: <String, String>{
        'Authorization': 'Bearer $token',
        'Accept': 'application/json',
      },
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw AgentStreamException(
        'Agent 停止失败（HTTP ${response.statusCode}）',
        statusCode: response.statusCode,
      );
    }
  }

  Uri _join(String path) {
    final normalizedBase = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;
    return Uri.parse('$normalizedBase$path');
  }
}
