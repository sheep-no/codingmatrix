import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Account-scoped store for capability switches.
abstract interface class CapabilityPreferences {
  Future<Map<String, dynamic>?> read(String scope);
  Future<void> write(String scope, Map<String, dynamic> value);
}

class SharedPreferencesCapabilityPreferences implements CapabilityPreferences {
  const SharedPreferencesCapabilityPreferences();

  static const _prefix = 'codingmatrix.generation.flags.v1:';

  @override
  Future<Map<String, dynamic>?> read(String scope) async {
    final prefs = await SharedPreferences.getInstance();
    final value = prefs.getString('$_prefix$scope');
    if (value == null) return null;
    try {
      final decoded = jsonDecode(value);
      return decoded is Map<String, dynamic> ? decoded : null;
    } catch (_) {
      return null;
    }
  }

  @override
  Future<void> write(String scope, Map<String, dynamic> value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('$_prefix$scope', jsonEncode(value));
  }
}

final capabilityPreferencesProvider = Provider<CapabilityPreferences>((ref) {
  return const SharedPreferencesCapabilityPreferences();
});
