import 'dart:convert';
import 'dart:io';
import 'package:pointycastle/digests/sha256.dart';

import 'package:http/http.dart' as http;

import 'cloud_auth_client.dart';

/// Only GET/HEAD can be replayed once. Mutations always require user recovery.
class AuthenticatedClient extends http.BaseClient {
  AuthenticatedClient(this.auth, this.transport);
  final CloudAuthClient auth;
  final http.Client transport;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final session = auth.session;
    if (session == null) throw CloudAuthException('请重新登录');
    final ref = session.accessTokenRef;
    final headers = await auth.headers(request.url, ref);
    final safe = {'GET', 'HEAD'}.contains(request.method);
    final retry = safe ? http.Request(request.method, request.url) : null;
    request.headers.removeWhere(
      (key, _) => {
        'authorization',
        'cookie',
        'x-csrf-token',
      }.contains(key.toLowerCase()),
    );
    request.headers.addAll(headers);
    request.followRedirects = false;
    retry?.headers.addAll(request.headers);
    try {
      final response = await transport.send(request).timeout(auth.timeout);
      if (auth.session?.accessTokenRef != ref) {
        await response.stream.drain<void>().timeout(auth.timeout);
        throw CloudAuthException('认证上下文已切换');
      }
      if (response.statusCode != 401) return await _checked(response, safe);
      await response.stream.drain<void>().timeout(auth.timeout);
      if (auth.session?.accessTokenRef != ref) {
        throw CloudAuthException('认证上下文已切换');
      }
      await auth.refresh(rejectedToken: headers['Authorization']!.substring(7));
      if (retry == null) {
        throw CloudAuthException('认证已刷新；请求结果未知，请确认任务状态后手动恢复', statusCode: 401);
      }
      retry.headers.addAll(await auth.headers(retry.url, ref));
      retry.followRedirects = false;
      final retried = await transport.send(retry).timeout(auth.timeout);
      if (auth.session?.accessTokenRef != ref) {
        await retried.stream.drain<void>().timeout(auth.timeout);
        throw CloudAuthException('认证上下文已切换');
      }
      if (retried.statusCode == 401) {
        await retried.stream.drain<void>().timeout(auth.timeout);
        await auth.logout();
        throw CloudAuthException('登录已失效，请重新登录', statusCode: 401);
      }
      return await _checked(retried, safe);
    } on CloudAuthException {
      rethrow;
    } catch (_) {
      throw CloudAuthException(
        safe ? '网络请求失败，请重试' : '连接中断，请求结果未知，请确认任务状态后手动恢复',
      );
    }
  }

  Future<http.StreamedResponse> _checked(
    http.StreamedResponse response,
    bool safe,
  ) async {
    if (response.statusCode >= 300) {
      await response.stream.drain<void>().timeout(auth.timeout);
      throw CloudAuthException(
        '请求失败（HTTP ${response.statusCode}）${safe ? '' : '，请确认任务状态后手动恢复'}',
        statusCode: response.statusCode,
      );
    }
    return http.StreamedResponse(
      response.stream.timeout(auth.timeout).handleError((Object _) {
        throw CloudAuthException('响应连接中断，请确认任务状态后手动恢复');
      }),
      response.statusCode,
      headers: response.headers,
      request: response.request,
      contentLength: response.contentLength,
      reasonPhrase: response.reasonPhrase,
    );
  }

  Future<Object?> requestJson(
    String path, {
    String method = 'GET',
    Object? body,
  }) async {
    final request = http.Request(method, Uri.parse(auth.baseUrl).resolve(path));
    request.headers['Accept'] = 'application/json';
    if (body != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    final response = await http.Response.fromStream(await send(request));
    try {
      return jsonDecode(response.body);
    } on FormatException {
      throw CloudAuthException('服务响应 JSON 格式错误');
    }
  }

  Future<Stream<List<int>>> sendJsonStream(String path, Object body) async {
    final request = http.Request('POST', Uri.parse(auth.baseUrl).resolve(path));
    request.headers['Accept'] = 'text/plain';
    request.headers['Content-Type'] = 'application/json';
    request.body = jsonEncode(body);
    final response = await send(request);
    return response.stream;
  }

  Future<Map<String, dynamic>> uploadFile(String path) async {
    final request = http.MultipartRequest(
      'POST',
      Uri.parse(auth.baseUrl).resolve('/api/v1/files/upload'),
    );
    request.files.add(await http.MultipartFile.fromPath('file', path));
    final response = await http.Response.fromStream(await send(request));
    final decoded = jsonDecode(response.body);
    return Map<String, dynamic>.from(decoded as Map);
  }

  Future<Map<String, dynamic>> uploadFileResumable(String path) async {
    final file = File(path);
    final length = await file.length();
    final bytes = await file.readAsBytes();
    final digest = SHA256Digest()
        .process(bytes)
        .map((byte) => byte.toRadixString(16).padLeft(2, '0'))
        .join();
    final name = path.split(Platform.pathSeparator).last;
    final init =
        await requestJson(
              '/api/v1/files/upload/init?filename=${Uri.encodeQueryComponent(name)}&file_size=$length&file_hash=$digest',
              method: 'POST',
            )
            as Map;
    final fileId = '${init['file_id']}';
    if (init['status'] == 'exists') return Map<String, dynamic>.from(init);
    final chunkSize = (init['chunk_size'] as num?)?.toInt() ?? 5 * 1024 * 1024;
    final total =
        (init['total_chunks'] as num?)?.toInt() ??
        ((length + chunkSize - 1) ~/ chunkSize);
    final uploaded = {
      for (final item in (init['uploaded_chunks'] as List? ?? const []))
        (item as num).toInt(),
    };
    for (var index = 0; index < total; index++) {
      if (uploaded.contains(index)) continue;
      final start = index * chunkSize;
      final end = (start + chunkSize).clamp(0, bytes.length);
      final request = http.MultipartRequest(
        'POST',
        Uri.parse(auth.baseUrl).resolve(
          '/api/v1/files/upload/chunk/$fileId/$index?total_chunks=$total',
        ),
      );
      request.files.add(
        http.MultipartFile.fromBytes(
          'chunk',
          bytes.sublist(start, end),
          filename: 'chunk_$index',
        ),
      );
      final response = await http.Response.fromStream(await send(request));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudAuthException('分片上传失败：${response.statusCode}');
      }
    }
    return Map<String, dynamic>.from(
      await requestJson(
            '/api/v1/files/upload/merge/$fileId?filename=${Uri.encodeQueryComponent(name)}&file_hash=$digest&file_size=$length',
            method: 'POST',
          )
          as Map,
    );
  }

  // The provider owns the shared transport.
  @override
  void close() {}
}
