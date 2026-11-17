import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:codingmatrix_desktop/presentation/agent_stats_dialog.dart';

void main() {
  const usage = <String, Object?>{
    'total_tokens': 1234,
    'prompt_tokens': 800,
    'completion_tokens': 434,
    'total_messages': 12,
    'today_tokens': 120,
    'this_month_tokens': 1234,
    'extra_field': 7,
    'by_model': {'gpt-4o': {'tokens': 900}, 'deepseek': {'tokens': 334}},
  };
  const cache = <String, Object?>{
    'total_requests': 2,
    'cache_hits': 0,
    'cache_misses': 2,
    'hit_rate': 0.0,
    'cached_entries': 0,
    'cache_size_mb': 0.0,
    'vector_index_size': 0,
    'tech_index_groups': 0,
  };
  const learning = <String, Object?>{
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
      {
        'error_type': 'validation_error',
        'error_message': '多次修复失败',
        'frequency': 94,
        'success_rate': 0.0,
        'fix_description': '修复: 多次修复失败',
      },
    ],
  };
  const limits = <String, Object?>{
    'recommendations': {'free': 1, 'basic': 2, 'premium': 5, 'enterprise': 10},
  };

  Future<void> pumpDialog(WidgetTester tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: AgentStatsDialog(
            usage: usage,
            cache: cache,
            learning: learning,
            limits: limits,
          ),
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets('统计弹层按分组渲染可读指标', (tester) async {
    await pumpDialog(tester);

    expect(find.text('Agent 统计'), findsOneWidget);
    expect(find.text('Token 用量'), findsOneWidget);
    expect(find.text('1,234'), findsWidgets);
    expect(find.text('总 Token'), findsOneWidget);
    expect(find.text('模型 gpt-4o'), findsOneWidget);
    expect(find.text('缓存'), findsOneWidget);
    expect(find.text('命中率'), findsOneWidget);
    expect(find.text('0.0%'), findsWidgets);
    expect(find.text('学习统计'), findsOneWidget);
    expect(find.text('已学习模式'), findsOneWidget);
    expect(find.text('#1 validation error · 495 次 · 修复成功率 100.0%'), findsOneWidget);
    expect(find.text('2 条'), findsOneWidget);
    expect(find.text('处理方式：增加枚举校验'), findsNothing);
    expect(find.text('extra field'), findsOneWidget);
    expect(find.text('推荐并发上限'), findsOneWidget);
    expect(find.text('免费版'), findsOneWidget);
    expect(find.text('企业版'), findsOneWidget);
    expect(find.text('10'), findsOneWidget);
    expect(find.byType(Card), findsNWidgets(4));

    await tester.ensureVisible(find.text('展开全部 2 条'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('展开全部 2 条'));
    await tester.pump();

    expect(find.text('收起错误列表'), findsOneWidget);
    expect(find.text('处理方式：增加枚举校验'), findsOneWidget);
  });

  testWidgets('统计弹层不再暴露原始 JSON 键名', (tester) async {
    await pumpDialog(tester);

    expect(find.textContaining('{'), findsNothing);
    expect(find.textContaining('by_model'), findsNothing);
    expect(find.textContaining('top_errors'), findsNothing);
    expect(find.textContaining('recommendations'), findsNothing);
    expect(find.textContaining('error_type'), findsNothing);
  });

  testWidgets('空数据与异常结构给出占位而不是崩溃', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: AgentStatsDialog(usage: null, cache: {}, learning: null, limits: 'oops'),
        ),
      ),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.text('暂无模型用量'), findsOneWidget);
    expect(find.text('暂无缓存数据'), findsOneWidget);
    expect(find.text('暂无学习记录'), findsOneWidget);
    expect(find.text('暂无推荐值'), findsOneWidget);
  });

  testWidgets('超长错误信息默认折叠，展开后完整显示', (tester) async {
    final long = List.generate(40, (i) => '第$i行错误内容').join('\n');
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AgentStatsDialog(
            usage: usage,
            cache: cache,
            learning: {
              'top_errors': [
                {'error_type': 'validation_error', 'error_message': long, 'frequency': 1},
              ],
            },
            limits: limits,
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('展开全部 1 条'), findsOneWidget);
    expect(find.text(long), findsNothing);

    await tester.ensureVisible(find.text('展开全部 1 条'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('展开全部 1 条'));
    await tester.pump();

    expect(find.text('收起错误列表'), findsOneWidget);
    expect(find.text(long), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('后端文本里的 HTML 换行实体被还原', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: AgentStatsDialog(
            usage: usage,
            cache: cache,
            learning: {
              'top_errors': [
                {
                  'error_type': 'validation_error',
                  'error_message': '第一行&#10;第二行&amp;结束',
                  'frequency': 3,
                },
              ],
            },
            limits: limits,
          ),
        ),
      ),
    );
    await tester.pump();

    await tester.ensureVisible(find.text('展开全部 1 条'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('展开全部 1 条'));
    await tester.pump();

    expect(find.text('第一行\n第二行&结束'), findsOneWidget);
    expect(find.textContaining('&#10;'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
