import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract interface class SessionStorage {
  Future<String?> read();
  Future<void> write(String value);
  Future<void> delete();
}

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

  Future<Map<String, dynamic>?> loadSession() async {
    await _writes;
    final value = await storage?.read();
    if (value == null) return null;
    return jsonDecode(value) as Map<String, dynamic>;
  }

  // Serialize storage operations so logout always follows an in-flight write.
  Future<void> saveSession(Map<String, dynamic> session) {
    final value = jsonEncode(session);
    final operation = _writes.then((_) async => storage?.write(value));
    _writes = operation.catchError((Object _) {});
    return operation;
  }

  Future<void> clearSession() {
    clear();
    final operation = _writes.then((_) async => storage?.delete());
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
