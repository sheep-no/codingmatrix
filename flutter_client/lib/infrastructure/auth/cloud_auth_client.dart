import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../domain/models/auth_session.dart';
import 'credential_store.dart';
import 'session_cookies.dart';

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
    required String baseUrl,
    required this.httpClient,
    required this.credentialStore,
    this.csrfPath = '/api/v1/csrf-token',
    this.loginPath = '/api/v1/login',
    this.timeout = const Duration(seconds: 20),
  }) : _baseUrl = normalizeBaseUrl(baseUrl),
       _cookies = SessionCookies(Uri.parse(normalizeBaseUrl(baseUrl)));

  String _baseUrl;
  String get baseUrl => _baseUrl;
  final Duration timeout;
  final http.Client httpClient;
  final CredentialStore credentialStore;
  final String csrfPath;
  final String loginPath;
  SessionCookies _cookies;
  AuthSession? session;
  String? _account;
  DateTime? _expiresAt;
  int _epoch = 0;
  Future<AuthSession>? _refreshing;
  void Function(AuthSession?)? onSessionChanged;

  static String normalizeBaseUrl(String value) {
    final uri = Uri.tryParse(value.trim());
    if (uri == null ||
        !{'http', 'https'}.contains(uri.scheme) ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        (uri.path.isNotEmpty && uri.path != '/')) {
      throw CloudAuthException('请输入有效的 HTTP(S) 服务地址（不含路径或凭据）');
    }
    return uri.origin;
  }

  void _check(int epoch) {
    if (epoch != _epoch) throw CloudAuthException('认证上下文已切换');
  }

  Future<http.Response> _request(
    String method,
    String path,
    SessionCookies cookies, {
    Object? body,
  }) async {
    final uri = _join(path);
    final request = http.Request(method, uri)..followRedirects = false;
    request.headers['Cookie'] = cookies.header(uri);
    final csrf = cookies.value('csrf_token', uri);
    if (csrf != null) request.headers['X-CSRF-Token'] = csrf;
    if (body != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    try {
      final response = await http.Response.fromStream(
        await httpClient.send(request).timeout(timeout),
      ).timeout(timeout);
      cookies.merge(response.headers['set-cookie'], uri);
      if (response.statusCode != 200) {
        throw CloudAuthException(
          '认证请求失败（HTTP ${response.statusCode}）',
          statusCode: response.statusCode,
        );
      }
      return response;
    } on CloudAuthException {
      rethrow;
    } catch (_) {
      throw CloudAuthException('认证连接失败，请检查网络后重试');
    }
  }

  Future<String> fetchCsrfToken() async {
    final epoch = _epoch;
    await _request('GET', csrfPath, _cookies);
    _check(epoch);
    final token = _cookies.value('csrf_token', _join(loginPath));
    if (token == null || token.isEmpty) {
      throw CloudAuthException('CSRF Token 缺失');
    }
    return token;
  }

  Future<AuthSession> login({
    required String email,
    required String password,
    String? serviceUrl,
  }) async {
    final nextUrl = normalizeBaseUrl(serviceUrl ?? baseUrl);
    final clearing = logout();
    final epoch = _epoch;
    await clearing;
    _check(epoch);
    _baseUrl = nextUrl;
    _account = email.trim().toLowerCase();
    _cookies = SessionCookies(Uri.parse(baseUrl));
    final cookies = _cookies;
    try {
      await fetchCsrfToken();
      _check(epoch);
      final response = await _request(
        'POST',
        loginPath,
        cookies,
        body: {'email': email.trim(), 'password': password},
      );
      _check(epoch);
      return await _accept(response, epoch);
    } catch (_) {
      if (epoch == _epoch) await logout();
      rethrow;
    }
  }

  Future<AuthSession> _accept(http.Response response, int epoch) async {
    try {
      _check(epoch);
      final payload = jsonDecode(response.body) as Map<String, dynamic>;
      final token = payload['access_token'] as String;
      if (token.isEmpty) throw const FormatException();
      final claims = _claims(token);
      final oldToken = session == null
          ? null
          : credentialStore.read(session!.accessTokenRef);
      if (oldToken != null && _claims(oldToken)['sub'] != claims['sub']) {
        throw const FormatException('Account changed');
      }
      _expiresAt = claims['exp'] is num
          ? DateTime.fromMillisecondsSinceEpoch(
              (claims['exp'] as num).toInt() * 1000,
              isUtc: true,
            )
          : DateTime.now();
      final ref =
          session?.accessTokenRef ?? credentialStore.storeAccessToken(token);
      credentialStore.replace(ref, token);
      final next = AuthSession(
        username: payload['username'] as String? ?? _account!,
        permissionLevel: payload['permission_level'] as String? ?? 'normal',
        accessTokenRef: ref,
      );
      await credentialStore.saveSession({
        'version': 1,
        'base_url': baseUrl,
        'account': _account,
        'session': next.toJson(),
        'access_token': token,
        'expires_at': _expiresAt!.toUtc().toIso8601String(),
        'cookies': _cookies.toJson(),
      });
      _check(epoch);
      session = next;
      onSessionChanged?.call(next);
      return next;
    } on CloudAuthException {
      rethrow;
    } catch (_) {
      throw CloudAuthException('认证响应或安全存储不可用，请重新登录');
    }
  }

  Map<String, dynamic> _claims(String token) {
    try {
      return jsonDecode(
            utf8.decode(
              base64Url.decode(base64Url.normalize(token.split('.')[1])),
            ),
          )
          as Map<String, dynamic>;
    } catch (_) {
      return {};
    }
  }

  Future<AuthSession?> restore() async {
    final epoch = _epoch;
    try {
      final saved = await credentialStore.loadSession();
      _check(epoch);
      if (saved == null) return null;
      if (saved['version'] != 1) throw const FormatException();
      _baseUrl = normalizeBaseUrl(saved['base_url'] as String);
      _account = saved['account'] as String;
      if (_account!.isEmpty) throw const FormatException();
      _cookies = SessionCookies(Uri.parse(baseUrl))
        ..restore(saved['cookies'] as List);
      final token = saved['access_token'] as String;
      final metadata = Map<String, dynamic>.from(saved['session'] as Map);
      metadata['access_token_ref'] = credentialStore.storeAccessToken(token);
      session = AuthSession.fromJson(metadata);
      _expiresAt = DateTime.parse(saved['expires_at'] as String);
      // The server verifies the refresh cookie before a restored account is shown.
      return await refresh();
    } catch (_) {
      if (epoch == _epoch) await logout();
      rethrow;
    }
  }

  Future<AuthSession> refresh({String? rejectedToken}) {
    if (session == null) return Future.error(CloudAuthException('请重新登录'));
    if (rejectedToken != null &&
        credentialStore.read(session!.accessTokenRef) != rejectedToken) {
      return Future.value(session!);
    }
    if (_refreshing != null) return _refreshing!;
    final epoch = _epoch;
    return _refreshing = _refresh().whenComplete(() {
      if (epoch == _epoch) _refreshing = null;
    });
  }

  Future<AuthSession> _refresh() async {
    final epoch = _epoch;
    try {
      final cookies = _cookies;
      if (cookies.value('refresh_token', _join('/api/v1/refresh')) == null) {
        throw CloudAuthException('登录已过期，请重新登录');
      }
      await fetchCsrfToken();
      _check(epoch);
      final response = await _request('POST', '/api/v1/refresh', cookies);
      _check(epoch);
      return await _accept(response, epoch);
    } catch (_) {
      if (epoch == _epoch) await logout();
      throw CloudAuthException('登录已过期或刷新失败，请重新登录');
    }
  }

  Future<Map<String, String>> headers(Uri uri, String ref) async {
    final epoch = _epoch;
    if (uri.origin != Uri.parse(baseUrl).origin ||
        !uri.path.startsWith('/api/')) {
      throw CloudAuthException('请求地址与认证服务不匹配');
    }
    if (session?.accessTokenRef != ref) throw CloudAuthException('登录凭据已失效');
    if (_expiresAt == null ||
        !_expiresAt!.isAfter(DateTime.now().add(const Duration(seconds: 30)))) {
      await refresh();
    }
    if (_cookies.value('csrf_token', uri) == null) await fetchCsrfToken();
    _check(epoch);
    final token = credentialStore.read(ref);
    if (token == null) throw CloudAuthException('登录凭据已失效');
    return {
      'Authorization': 'Bearer $token',
      'Cookie': _cookies.header(uri),
      if (_cookies.value('csrf_token', uri) case final String csrf)
        'X-CSRF-Token': csrf,
    };
  }

  Future<void> logout() async {
    _epoch++;
    session = null;
    _account = null;
    _expiresAt = null;
    _cookies = SessionCookies(Uri.parse(baseUrl));
    _refreshing = null;
    onSessionChanged?.call(null);
    await credentialStore.clearSession();
  }

  void detach() {
    _epoch++;
    credentialStore.clear();
    session = null;
    _cookies = SessionCookies(Uri.parse(baseUrl));
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
