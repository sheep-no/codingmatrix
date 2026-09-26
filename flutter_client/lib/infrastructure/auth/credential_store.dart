import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract interface class SessionStorage {
  Future<String?> read();
  Future<void> write(String value);
  Future<void> delete();
}

/// The platform secure storage backend refused the operation, for example a
/// Linux host without an unlocked Secret Service keyring. Sessions cannot be
/// persisted until the host provides one.
class SecureStorageUnavailableException implements Exception {
  const SecureStorageUnavailableException();

  @override
  String toString() => 'secure storage unavailable';
}

const secureStorageUnavailableMessage =
    '系统安全存储不可用，登录状态无法在本机保存。请先安装并解锁系统密钥环，再重试。';

class DeviceSessionStorage implements SessionStorage {
  const DeviceSessionStorage();

  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );
  static const _key = 'codingmatrix.auth.session.v1';

  @override
  Future<String?> read() => _storage.read(key: _key);
  @override
  Future<void> write(String value) => _storage.write(key: _key, value: value);
  @override
  Future<void> delete() => _storage.delete(key: _key);
}

/// Production injects device storage; tests can use an isolated memory store.
class CredentialStore {
  CredentialStore({this.storage});
  final SessionStorage? storage;
  Future<void> _writes = Future<void>.value();
  final Map<String, String> _tokens = <String, String>{};
  int _sequence = 0;

  String storeAccessToken(String token) {
    _sequence += 1;
    final ref = 'token-$_sequence';
    _tokens[ref] = token;
    return ref;
  }

  String? read(String accessTokenRef) => _tokens[accessTokenRef];

  void replace(String ref, String token) => _tokens[ref] = token;

  // Any backend failure means the session cannot be persisted, so report it as
  // such instead of leaking a platform-specific error.
  Future<T> _guard<T>(Future<T> Function() operation) async {
    try {
      return await operation();
    } catch (_) {
      throw const SecureStorageUnavailableException();
    }
  }

  Future<Map<String, dynamic>?> loadSession() async {
    await _writes;
    final value = await _guard(() async => storage?.read());
    if (value == null) return null;
    return jsonDecode(value) as Map<String, dynamic>;
  }

  // Serialize storage operations so logout always follows an in-flight write.
  Future<void> saveSession(Map<String, dynamic> session) {
    final value = jsonEncode(session);
    final operation = _writes.then(
      (_) => _guard(() async => storage?.write(value)),
    );
    _writes = operation.catchError((Object _) {});
    return operation;
  }

  Future<void> clearSession() {
    clear();
    final operation = _writes.then(
      (_) => _guard(() async => storage?.delete()),
    );
    _writes = operation.catchError((Object _) {});
    return operation;
  }

  void delete(String accessTokenRef) {
    _tokens.remove(accessTokenRef);
  }

  void clear() {
    _tokens.clear();
  }
}
