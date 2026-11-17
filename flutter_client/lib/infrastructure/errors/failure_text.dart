import 'dart:convert';
import 'dart:async';

/// Readable root-cause text for transport failures.
///
/// The pages used to show one generic line for every stream failure, which hid
/// whether the cause was a wrong path, an expired token, a full disk or a
/// broken compression header. These helpers keep the reason actionable while
/// still naming the HTTP status for diagnostics.
String httpFailureReason(int statusCode) {
  return switch (statusCode) {
    400 => '请求参数有误',
    401 => '登录已失效，请重新登录',
    403 => '没有权限执行该操作',
    404 => '接口不存在或资源已被删除，请核对服务地址与版本',
    405 => '请求方法不被支持，请核对接口契约',
    409 => '任务状态冲突，可能已在其他地方执行',
    422 => '请求参数校验未通过，请检查必填项',
    429 => '请求过于频繁，请稍后重试',
    500 => '服务内部错误，通常是模型服务未配置或后端故障',
    502 => '上游服务不可用，请检查模型服务配置',
    503 => '服务暂不可用，请稍后重试',
    504 => '服务响应超时，请稍后重试',
    507 => '服务器磁盘空间不足，请清理后重试',
    _ => statusCode >= 500 ? '服务端异常，请稍后重试' : '请求失败',
  };
}

/// `reason（HTTP 404）` keeps the readable cause first and the code second.
String httpFailureText(int statusCode) =>
    '${httpFailureReason(statusCode)}（HTTP $statusCode）';

/// Extracts the human-readable cause from a JSON error body.
///
/// The backend answers with `{"code": ..., "message": ..., "details": ...}` or
/// FastAPI's `{"detail": ...}`. Both carry the actionable part (for example
/// "获取 Key 列表失败"), which used to be dropped while only the status code
/// survived. Plain-text and HTML bodies are ignored: they are arbitrary server
/// output and could echo secrets back into the UI.
String? serverFailureDetail(String body) {
  final trimmed = body.trim();
  if (trimmed.isEmpty) return null;
  Object? decoded;
  try {
    decoded = jsonDecode(trimmed);
  } on FormatException {
    return null;
  }
  if (decoded is Map) {
    for (final key in ['message', 'detail', 'error']) {
      final value = decoded[key];
      if (value is String && value.trim().isNotEmpty) {
        final detail = _flattenDetail(value.trim());
        if (detail.isNotEmpty) return _shorten(detail);
      }
      // FastAPI 会把字典形式的 detail 包成 {"detail": {"code": ..., "message": ...}}。
      if (value is Map) {
        final nested = value['message'] ?? value['detail'];
        if (nested is String && nested.trim().isNotEmpty) {
          return _shorten(nested.trim());
        }
      }
    }
    return null;
  }
  return null;
}

/// 全局异常处理会把字典 detail 转成 Python repr，取出其中的可读 message。
String _flattenDetail(String value) {
  final match = RegExp(r"'message':\s*'([^']*)'").firstMatch(value);
  return match?.group(1) ?? value;
}

/// Storage (Redis) outages surface as generic 500/403 errors. The provider key
/// list and submit both live in Redis, so name the real dependency instead of
/// asking the user to retry an input that is already valid.
bool isStorageFailure(String? error) {
  if (error == null) return false;
  final text = error.toLowerCase();
  return text.contains('存储') ||
      text.contains('获取 key 列表失败') ||
      text.contains('redis');
}

// Guards the UI against a multi-kilobyte stack trace landing in a one-line text.
String _shorten(String value) =>
    value.length <= 200 ? value : '${value.substring(0, 200)}…';

/// Describes a stream failure so the page can say *why* it stopped.
String streamFailureText(Object error) {
  final text = error.toString();
  if (text.contains('Filter error') || text.contains('bad data')) {
    return '响应解压失败：服务端声明的压缩头与响应内容不一致，请联系后端检查流式接口的 Content-Encoding';
  }
  if (error is TimeoutException) {
    return '响应超时，服务端可能仍在执行，可稍后查询状态';
  }
  if (text.contains('SocketException') || text.contains('connection lost')) {
    return '网络连接中断，请检查网络后重试';
  }
  if (error is FormatException) {
    return '响应内容格式异常，已收到的数据不完整';
  }
  // HTTP failures already carry a readable cause plus the status code.
  if (RegExp(r'HTTP \d{3}').hasMatch(text)) return text;
  return '响应流异常：$text';
}
