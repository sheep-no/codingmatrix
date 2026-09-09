import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../domain/models/provider_key.dart';
import '../infrastructure/provider/provider_key_client.dart';
import 'auth_controller.dart';

class ProviderKeyState {
  const ProviderKeyState({
    this.items = const [],
    this.loading = false,
    this.error,
    this.selectedToken,
  });
  final String? selectedToken;
  ProviderKeySummary? get selected {
    for (final item in items) {
      if (item.token == selectedToken && item.isUsable) return item;
    }
    return null;
  }

  final List<ProviderKeySummary> items;
  final bool loading;
  final String? error;
  ProviderKeyState copyWith({
    List<ProviderKeySummary>? items,
    bool? loading,
    String? error,
    bool clearError = false,
  }) => ProviderKeyState(
    items: items ?? this.items,
    loading: loading ?? this.loading,
    error: clearError ? null : (error ?? this.error),
    selectedToken: selectedToken,
  );
}

class ProviderKeyController extends StateNotifier<ProviderKeyState> {
  ProviderKeyController(this.client) : super(const ProviderKeyState());
  final ProviderKeyClient client;
  void select(ProviderKeySummary item) {
    if (item.isUsable) {
      state = ProviderKeyState(items: state.items, selectedToken: item.token);
    }
  }

  @override
  set state(ProviderKeyState value) {
    if (mounted) super.state = value;
  }

  Future<void> load() async {
    if (!mounted) return;
    state = state.copyWith(loading: true, clearError: true);
    try {
      state = state.copyWith(items: await client.list(), loading: false);
    } catch (_) {
      if (!mounted) return;
      state = state.copyWith(loading: false, error: 'Provider 配置加载失败，请重试');
    }
  }

  Future<bool> add({
    required String key,
    required String provider,
    String remark = '',
  }) async {
    state = state.copyWith(loading: true, clearError: true);
    try {
      await client.submit(key: key, provider: provider, remark: remark);
      await load();
      return true;
    } catch (_) {
      if (!mounted) return false;
      state = state.copyWith(
        loading: false,
        error: 'Provider Key 提交失败，请检查输入后重试',
      );
      return false;
    }
  }

  Future<void> toggle(ProviderKeySummary item) async {
    if (state.loading) return;
    state = state.copyWith(loading: true, clearError: true);
    try {
      await client.setEnabled(item.token, !item.enabled);
      await load();
    } catch (_) {
      if (!mounted) return;
      state = state.copyWith(loading: false, error: '更新 Provider 状态失败，请重试');
    }
  }

  Future<void> test(ProviderKeySummary item) async {
    if (state.loading) return;
    state = state.copyWith(loading: true, clearError: true);
    try {
      await client.test(item.token);
      await load();
    } catch (_) {
      if (!mounted) return;
      state = state.copyWith(loading: false, error: 'Provider Key 测试失败，请重试');
    }
  }

  Future<void> remove(ProviderKeySummary item) async {
    if (state.loading) return;
    state = state.copyWith(loading: true, clearError: true);
    try {
      await client.delete(item.token);
      await load();
    } catch (_) {
      if (!mounted) return;
      state = state.copyWith(loading: false, error: '删除 Provider Key 失败，请重试');
    }
  }
}

final providerKeyControllerProvider =
    StateNotifierProvider<ProviderKeyController, ProviderKeyState>((ref) {
      ref.watch(
        authControllerProvider.select((value) => value.session?.accessTokenRef),
      );
      return ProviderKeyController(
        ProviderKeyClient(ref.watch(authenticatedClientProvider)),
      );
    });
