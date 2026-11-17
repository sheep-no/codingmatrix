import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/presentation/model_service_hint.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'agent_delivery_test.dart' show DeliveryApi;

const serverFailure = '请求失败（HTTP 500），请确认任务状态后手动恢复';

class ProbeApi extends DeliveryApi {
  ProbeApi(this.providers, this.keys)
    : super((path, _, __) async {
        if (path == '/api/v1/providers') {
          return providers;
        }
        if (path == '/api/v1/agent/apikeys') return keys;
        return null;
      });

  final Object? providers;
  final Object? keys;
  final paths = <String>[];

  @override
  Future<Object?> requestJson(
    String path, {
    String method = 'GET',
    Object? body,
    Duration? timeout,
  }) {
    paths.add(path);
    return super.requestJson(path, method: method, body: body, timeout: timeout);
  }
}

Future<void> pumpHint(WidgetTester tester, ProbeApi api, String error) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
      child: MaterialApp(home: Scaffold(body: ModelServiceHint(error: error))),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  test('只把模型服务类失败识别为配置问题', () {
    expect(isModelServiceFailure('服务内部错误，请稍后重试'), isTrue);
    expect(isModelServiceFailure('AI 回复生成失败，请稍后重试'), isTrue);
    expect(
      isModelServiceFailure(
        'LLM 流式调用失败: Qwen/Qwen3-8B - All providers failed. '
        'Last error: Provider siliconflow is not configured',
      ),
      isTrue,
    );
    expect(isModelServiceFailure(serverFailure), isTrue);
    expect(isModelServiceFailure('connection lost'), isFalse);
    expect(isModelServiceFailure(null), isFalse);
  });

  testWidgets('没有可用 provider 时展示未配置模型服务引导', (tester) async {
    final api = ProbeApi(const [], const []);
    await pumpHint(tester, api, serverFailure);

    expect(find.text('未配置模型服务'), findsOneWidget);
    expect(find.textContaining('还没有可用的模型服务授权'), findsOneWidget);
    expect(find.byKey(const Key('modelServiceConfigureButton')), findsOneWidget);
    expect(find.byKey(const Key('modelServiceRefreshButton')), findsOneWidget);
    expect(find.text(serverFailure), findsNothing);
    expect(api.paths, ['/api/v1/providers', '/api/v1/agent/apikeys']);
  });

  testWidgets('已启用动态 provider 时保留原始错误', (tester) async {
    final api = ProbeApi(
      const [
        {
          'id': 'p1',
          'name': '自定义',
          'base_url': 'https://api.example.com/v1',
          'protocol': 'openai',
          'enabled': true,
          'models': ['glm-4'],
        },
      ],
      const [],
    );
    await pumpHint(tester, api, serverFailure);

    expect(find.text('未配置模型服务'), findsNothing);
    expect(find.text(serverFailure), findsOneWidget);
    expect(api.paths, ['/api/v1/providers']);
  });

  testWidgets('只有停用的动态 provider 时由可用 Key 判定已配置', (tester) async {
    final api = ProbeApi(
      const [
        {
          'id': 'p1',
          'name': '停用供应商',
          'base_url': 'https://api.example.com/v1',
          'protocol': 'openai',
          'enabled': false,
          'models': <String>[],
        },
      ],
      [
        {
          'token': 't1',
          'provider': 'glm',
          'status': 'active',
          'enabled': true,
          'expires_at': DateTime.now()
              .add(const Duration(hours: 1))
              .toIso8601String(),
        },
      ],
    );
    await pumpHint(tester, api, serverFailure);

    expect(find.text('未配置模型服务'), findsNothing);
    expect(find.text(serverFailure), findsOneWidget);
  });

  testWidgets('探测失败时不误报未配置', (tester) async {
    final api = ProbeApi('broken', 'broken');
    await pumpHint(tester, api, serverFailure);

    expect(find.text('未配置模型服务'), findsNothing);
    expect(find.text(serverFailure), findsOneWidget);
  });

  testWidgets('其他错误不触发探测并直接展示原文', (tester) async {
    final api = ProbeApi(const [], const []);
    await pumpHint(tester, api, 'connection lost');

    expect(find.text('connection lost'), findsOneWidget);
    expect(find.text('未配置模型服务'), findsNothing);
    expect(api.paths, isEmpty);
  });
}
