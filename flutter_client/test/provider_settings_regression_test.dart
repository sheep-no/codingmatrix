import 'package:codingmatrix_desktop/application/provider_key_controller.dart';
import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/authenticated_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/cloud_auth_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/credential_store.dart';
import 'package:codingmatrix_desktop/infrastructure/provider/provider_key_client.dart';
import 'package:codingmatrix_desktop/presentation/provider_settings_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

class RecordingApi extends AuthenticatedClient {
  RecordingApi(this.handler)
    : super(
        CloudAuthClient(
          baseUrl: 'https://example.com',
          httpClient: http.Client(),
          credentialStore: CredentialStore(),
        ),
        http.Client(),
      );
  final Future<Object?> Function(String, String, Object?) handler;
  @override
  Future<Object?> requestJson(
    String path, {
    String method = 'GET',
    Object? body,
    Duration? timeout,
  }) => handler(path, method, body);
}

void main() {
  testWidgets('账号重置后下拉回到默认 Provider，不再显示上一个账号的选择', (
    tester,
  ) async {
    final container = ProviderContainer(
      overrides: [
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(RecordingApi((_, __, ___) async => <Object?>[])),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('deepseek').last);
    await tester.pumpAndSettle();
    expect(find.text('deepseek'), findsOneWidget);
    FormFieldState<String> field() => tester.state<FormFieldState<String>>(
      find.byType(DropdownButtonFormField<String>),
    );
    expect(field().value, 'deepseek');

    // `_resetAccount` runs on a changed base URL (same hook as account switch);
    // it resets `provider` to the first entry and rebuilds the page.
    container.read(apiBaseUrlProvider.notifier).state = 'https://other.example';
    await tester.pumpAndSettle();

    expect(field().value, 'siliconflow');
    expect(find.text('siliconflow'), findsOneWidget);
    expect(find.text('deepseek'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('存储不可用时给出 Redis 提示而不是只让重试', (tester) async {
    final container = ProviderContainer(
      overrides: [
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(
              RecordingApi(
                (_, __, ___) async => throw CloudAuthException(
                  '获取 Key 列表失败（HTTP 500）',
                  statusCode: 500,
                ),
              ),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.text('Provider 配置加载失败：获取 Key 列表失败（HTTP 500）'),
      findsOneWidget,
    );
    expect(find.textContaining('Redis'), findsOneWidget);
  });
}
