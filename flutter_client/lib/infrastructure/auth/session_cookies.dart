import 'dart:io';

/// An origin-bound native jar for the two cookies in the backend contract.
class SessionCookies {
  SessionCookies(this.origin);
  final Uri origin;
  final Map<String, Map<String, dynamic>> _cookies = {};

  void merge(String? header, Uri source, {DateTime? now}) {
    if (header == null || source.origin != origin.origin) return;
    final time = now ?? DateTime.now();
    // HTTP combines duplicate headers; the comma in Expires is not a separator.
    for (final part in header.split(RegExp(r',(?=\s*[^\s;,=]+=)'))) {
      try {
        final cookie = Cookie.fromSetCookieValue(part.trim());
        if (!{'refresh_token', 'csrf_token'}.contains(cookie.name)) continue;
        final domain = cookie.domain
            ?.replaceFirst(RegExp(r'^\.'), '')
            .toLowerCase();
        if (domain != null && domain != origin.host) continue;
        if (cookie.secure && source.scheme != 'https') continue;
        final path = cookie.path?.startsWith('/') == true
            ? cookie.path!
            : source.path.lastIndexOf('/') <= 0
            ? '/'
            : source.path.substring(0, source.path.lastIndexOf('/'));
        final expires = cookie.maxAge != null
            ? time.add(Duration(seconds: cookie.maxAge!))
            : cookie.expires;
        final key = '${cookie.name}:$path';
        if (cookie.value.isEmpty ||
            (expires != null && !expires.isAfter(time))) {
          _cookies.remove(key);
        } else {
          _cookies[key] = {
            'name': cookie.name,
            'value': cookie.value,
            'path': path,
            'secure': cookie.secure,
            'expires': expires?.toUtc().toIso8601String(),
          };
        }
      } on FormatException {
        // Ignore malformed cookies without logging credential material.
      }
    }
  }

  List<Map<String, dynamic>> _matching(Uri target, DateTime now) {
    if (target.origin != origin.origin) return [];
    return _cookies.values.where((cookie) {
      final expires = DateTime.tryParse(cookie['expires'] as String? ?? '');
      final path = cookie['path'] as String;
      return (expires == null || expires.isAfter(now)) &&
          (cookie['secure'] != true || target.scheme == 'https') &&
          (target.path == path ||
              target.path.startsWith(path.endsWith('/') ? path : '$path/'));
    }).toList()..sort(
      (a, b) =>
          (b['path'] as String).length.compareTo((a['path'] as String).length),
    );
  }

  String header(Uri target, {DateTime? now}) => _matching(
    target,
    now ?? DateTime.now(),
  ).map((cookie) => '${cookie['name']}=${cookie['value']}').join('; ');

  String? value(String name, Uri target) {
    for (final cookie in _matching(target, DateTime.now())) {
      if (cookie['name'] == name) return cookie['value'] as String;
    }
    return null;
  }

  List<Map<String, dynamic>> toJson() => _cookies.values.toList();

  void restore(List<dynamic> cookies) {
    for (final item in cookies) {
      final cookie = Map<String, dynamic>.from(item as Map);
      if (!{'csrf_token', 'refresh_token'}.contains(cookie['name']) ||
          cookie['value'] is! String ||
          cookie['path'] is! String ||
          !(cookie['path'] as String).startsWith('/')) {
        throw const FormatException('Invalid cookie record');
      }
      _cookies['${cookie['name']}:${cookie['path']}'] = cookie;
    }
  }
}
