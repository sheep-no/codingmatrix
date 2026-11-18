import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../application/model_service_controller.dart';
import 'provider_settings_page.dart';

/// Server failures that surface when no provider can answer the request.
///
/// The backend currently collapses every provider error into a generic 500, so
/// the client pairs this text check with a provider probe before claiming the
/// account is unconfigured.
bool isModelServiceFailure(String? error) {
  if (error == null) return false;
  final text = error.toLowerCase();
  return text.contains('服务内部错误') ||
      text.contains('ai 回复生成失败') ||
      text.contains('all providers failed') ||
      text.contains('is not configured') ||
      text.contains('http 500');
}

/// Renders the original error, or a configuration guide when the account has
/// no enabled provider and the error looks like a provider outage.
class ModelServiceHint extends ConsumerWidget {
  const ModelServiceHint({required this.error, super.key});

  final String error;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (!isModelServiceFailure(error)) {
      return _RawError(error: error);
    }
    final status = ref.watch(modelServiceStatusProvider);
    return status.maybeWhen(
      data: (value) => value.known && !value.configured
          ? const _Guide()
          : _RawError(error: error),
      orElse: () => _RawError(error: error),
    );
  }
}

class _Guide extends ConsumerWidget {
  const _Guide();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return Card(
      color: theme.colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '未配置模型服务',
              style: theme.textTheme.titleSmall?.copyWith(
                color: theme.colorScheme.onErrorContainer,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              '当前账号还没有可用的模型服务授权。聊天、Agent 工作台与 GirlAI 需要模型服务，'
              '请先添加 Provider API Key 或动态供应商后重试。',
              style: TextStyle(color: theme.colorScheme.onErrorContainer),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                FilledButton(
                  key: const Key('modelServiceConfigureButton'),
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => const ProviderSettingsPage(),
                    ),
                  ),
                  child: const Text('前往 Provider 授权'),
                ),
                TextButton(
                  key: const Key('modelServiceRefreshButton'),
                  onPressed: () => ref.invalidate(modelServiceStatusProvider),
                  child: const Text('重新检测'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _RawError extends StatelessWidget {
  const _RawError({required this.error});

  final String error;

  @override
  Widget build(BuildContext context) {
    return Text(
      error,
      style: TextStyle(color: Theme.of(context).colorScheme.error),
    );
  }
}
