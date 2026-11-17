import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:codingmatrix_desktop/application/agent_session_providers.dart';
import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/presentation/agent_history_page.dart';
import 'agent_delivery_test.dart' show DeliveryApi;

void main() {
  testWidgets('会话历史页的 Agent 统计弹层展示分组指标', (tester) async {
    final payloads = <String, Object?>{
      '/api/v1/agent/token-usage': {
        'total_tokens': 0,
        'prompt_tokens': 0,
        'completion_tokens': 0,
        'total_messages': 0,
        'today_tokens': 0,
        'this_month_tokens': 0,
        'by_model': <String, Object?>{},
      },
      '/api/v1/agent/cache/stats': {
        'total_requests': 2,
        'cache_hits': 0,
        'cache_misses': 2,
        'hit_rate': 0.0,
        'cached_entries': 0,
        'cache_size_mb': 0.0,
        'vector_index_size': 0,
        'tech_index_groups': 0,
      },
      '/api/v1/agent/learning/stats': {
        'learned_patterns': 46,
        'total_fixes_recorded': 727,
        'total_sessions': 0,
        'overall_success_rate': 0.0,
        'top_errors': [
          {
            'error_type': 'validation_error',
            'error_message': 'error1',
            'frequency': 495,
            'success_rate': 1.0,
            'fix_description': '修复: 增加枚举校验',
          },
        ],
      },
      '/api/v1/agent/concurrent-limits/recommended': {
        'recommendations': {'free': 1, 'basic': 2, 'premium': 5, 'enterprise': 10},
      },
    };
    final container = ProviderContainer(
      overrides: [
        agentSessionsProvider.overrideWith((_) async => []),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, _, __) async => payloads[path]),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AgentHistoryPage()),
      ),
    );
    await tester.pump();
    await tester.pump();

    await tester.tap(find.byTooltip('Agent 统计'));
    await tester.pump();
    await tester.pump();

    expect(find.text('Token 用量'), findsOneWidget);
    expect(find.text('消息数'), findsOneWidget);
    expect(find.text('命中率'), findsOneWidget);
    expect(find.text('已学习模式'), findsOneWidget);
    expect(find.text('#1 validation error · 495 次 · 修复成功率 100.0%'), findsOneWidget);
    expect(find.text('1 条'), findsOneWidget);
    expect(find.text('推荐并发上限'), findsOneWidget);
    expect(find.textContaining('{'), findsNothing);
    expect(find.textContaining('by_model'), findsNothing);

    await tester.ensureVisible(find.text('展开全部 1 条'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('展开全部 1 条'));
    await tester.pump();

    expect(find.text('处理方式：增加枚举校验'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
