import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../domain/models/auth_session.dart';
import 'credential_store.dart';

class CloudAuthException implements Exception {
  CloudAuthException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

/// CSRF double-submit login client for the CodingMatrix cloud API.
class CloudAuthClient {
  CloudAuthClient({
    required this.baseUrl,
    required this.httpClient,
    required this.credentialStore,
    this.csrfPath = '/api/v1/auth/csrf-token',
    this.loginPath = '/api/v1/auth/login',
  });

  final String baseUrl;
  final http.Client httpClient;
  final CredentialStore credentialStore;
  final String csrfPath;
  final String loginPath;

  Future<String> fetchCsrfToken() async {
    final response = await httpClient.get(_join(csrfPath));
    if (response.statusCode != 200) {
      throw CloudAuthException(
        _extractDetail(response, fallback: '获取 CSRF Token 失败'),
        statusCode: response.statusCode,
      );
    }

    String? token;
    try {
      final body = jsonDecode(response.body);
      if (body is Map && body['csrf_token'] is String) {
        token = body['csrf_token'] as String;
      }
    } on FormatException {
      token = null;
    }
    token ??= cookieValue(response.headers['set-cookie'], 'csrf_token');
    if (token == null || token.isEmpty) {
      throw CloudAuthException('CSRF Token 缺失');
    }
    return token;
  }

  Future<AuthSession> login({
    required String email,
    required String password,
  }) async {
    final csrfToken = await fetchCsrfToken();
    final response = await httpClient.post(
      _join(loginPath),
      headers: <String, String>{
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken,
        'Cookie': 'csrf_token=$csrfToken',
      },
      body: jsonEncode(<String, String>{
        'email': email,
        'password': password,
      }),
    );

    if (response.statusCode != 200) {
      throw CloudAuthException(
        _extractDetail(response, fallback: '登录失败'),
        statusCode: response.statusCode,
      );
    }

    final body = jsonDecode(response.body);
    if (body is! Map) {
      throw CloudAuthException('登录响应格式错误');
    }
    final payload = Map<String, dynamic>.from(body);
    final accessToken = payload['access_token'] as String?;
    if (accessToken == null || accessToken.isEmpty) {
      throw CloudAuthException('登录响应缺少 access_token');
    }

    final accessTokenRef = credentialStore.storeAccessToken(accessToken);
    return AuthSession(
      username: payload['username'] as String? ?? email,
      permissionLevel: payload['permission_level'] as String? ?? 'normal',
      tokenType: payload['token_type'] as String? ?? 'bearer',
      accessTokenRef: accessTokenRef,
    );
  }

  Uri _join(String path) {
    final normalizedBase = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;
    return Uri.parse('$normalizedBase$path');
  }
}

String? cookieValue(String? setCookie, String name) {
  if (setCookie == null || setCookie.isEmpty) {
    return null;
  }
  final match = RegExp('(?:^|,|\\s)$name=([^;\\s]+)').firstMatch(setCookie);
  return match?.group(1);
}

String _extractDetail(http.Response response, {required String fallback}) {
  try {
    final body = jsonDecode(response.body);
    if (body is Map && body['detail'] != null) {
      return body['detail'].toString();
    }
  } on FormatException {
    // Keep the HTTP fallback message.
  }
  if (response.body.isNotEmpty) {
    return response.body;
  }
  return fallback;
}
