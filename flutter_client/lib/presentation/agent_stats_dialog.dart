import 'package:flutter/material.dart';

/// Agent 统计弹层：四个统计接口各渲染成一张卡片。
///
/// 指标以「标签 + 数值」小块排布；高频错误默认只给摘要，展开后显示
/// 完整错误与处理方式。服务端新增的未知字段也会以可读形式追加。
class AgentStatsDialog extends StatelessWidget {
  const AgentStatsDialog({
    super.key,
    required this.usage,
    required this.cache,
    required this.learning,
    required this.limits,
  });

  final Object? usage;
  final Object? cache;
  final Object? learning;
  final Object? limits;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Agent 统计'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          key: const ValueKey('agentStatsContent'),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _UsageCard(usage),
              _CacheCard(cache),
              _LearningCard(learning),
              _LimitCard(limits),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('关闭'),
        ),
      ],
    );
  }
}

class _UsageCard extends StatelessWidget {
  const _UsageCard(this.payload);
  final Object? payload;

  @override
  Widget build(BuildContext context) {
    final data = _asMap(payload);
    final models = _asMap(data.remove('by_model'));
    final promptTokens = _asNumber(data['prompt_tokens']) ?? 0;
    final completionTokens = _asNumber(data['completion_tokens']) ?? 0;
    final hasTokenBreakdown = promptTokens > 0 || completionTokens > 0;
    if (!hasTokenBreakdown) {
      data.remove('prompt_tokens');
      data.remove('completion_tokens');
    }
    return _StatsCard(
      icon: Icons.toll_outlined,
      title: 'Token 用量',
      children: [
        _metricWrap(data, [
          'total_tokens',
          if (hasTokenBreakdown) 'prompt_tokens',
          if (hasTokenBreakdown) 'completion_tokens',
          'total_messages',
          'today_tokens',
          'this_month_tokens',
        ]),
        if (models.isEmpty)
          _emptyRow('暂无模型用量')
        else ...[
          _subTitle('按模型（总 Token）'),
          for (final entry in models.entries)
            _MetricRow('模型 ${entry.key}', _valueText(entry.key, entry.value)),
        ],
      ],
    );
  }
}

class _CacheCard extends StatelessWidget {
  const _CacheCard(this.payload);
  final Object? payload;

  @override
  Widget build(BuildContext context) {
    final data = _asMap(payload);
    final tiles = _metricTiles(data, const [
      'total_requests',
      'cache_hits',
      'cache_misses',
      'hit_rate',
      'cached_entries',
      'cache_size_mb',
      'vector_index_size',
      'tech_index_groups',
    ]);
    return _StatsCard(
      icon: Icons.memory_outlined,
      title: '缓存',
      children: [
        if (tiles.isEmpty)
          _emptyRow('暂无缓存数据')
        else
          Wrap(spacing: 8, runSpacing: 8, children: tiles),
      ],
    );
  }
}

class _LearningCard extends StatelessWidget {
  const _LearningCard(this.payload);
  final Object? payload;

  @override
  Widget build(BuildContext context) {
    final data = _asMap(payload);
    final errors = data.remove('top_errors');
    final items = errors is List
        ? errors.whereType<Map>().toList()
        : const <Map>[];
    return _StatsCard(
      icon: Icons.school_outlined,
      title: '学习统计',
      children: [
        _metricWrap(data, const [
          'learned_patterns',
          'total_fixes_recorded',
          'total_sessions',
          'overall_success_rate',
        ]),
        const SizedBox(height: 8),
        _ErrorList(items),
      ],
    );
  }
}

class _LimitCard extends StatelessWidget {
  const _LimitCard(this.payload);
  final Object? payload;

  @override
  Widget build(BuildContext context) {
    final data = _asMap(payload);
    final recommended = _asMap(data.remove('recommendations'));
    final tiles = <Widget>[
      ..._metricTiles(data, const <String>[]),
      for (final entry in recommended.entries)
        _MetricTile(_label(entry.key), _valueText(entry.key, entry.value)),
    ];
    return _StatsCard(
      icon: Icons.speed_outlined,
      title: '推荐并发上限',
      children: [
        if (tiles.isEmpty)
          _emptyRow('暂无推荐值')
        else
          Wrap(spacing: 8, runSpacing: 8, children: tiles),
      ],
    );
  }
}

/// 高频错误：默认展示前三条摘要，可展开为完整列表。
class _ErrorList extends StatefulWidget {
  const _ErrorList(this.items);
  final List<Map> items;

  @override
  State<_ErrorList> createState() => _ErrorListState();
}

class _ErrorListState extends State<_ErrorList> {
  static const _previewCount = 3;
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final items = widget.items;
    final shown = _expanded ? items : items.take(_previewCount).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Text('高频错误', style: TextStyle(fontWeight: FontWeight.w600)),
            const Spacer(),
            if (items.isNotEmpty) _subTitle('${items.length} 条'),
          ],
        ),
        if (items.isEmpty) _emptyRow('暂无学习记录'),
        for (var i = 0; i < shown.length; i++)
          _ErrorItem(index: i + 1, data: shown[i], summary: !_expanded),
        if (items.isNotEmpty)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              onPressed: () => setState(() => _expanded = !_expanded),
              style: TextButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 2),
                minimumSize: const Size(0, 28),
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              child: Text(_expanded ? '收起错误列表' : '展开全部 ${items.length} 条'),
            ),
          ),
      ],
    );
  }
}

class _ErrorItem extends StatelessWidget {
  const _ErrorItem({
    required this.index,
    required this.data,
    required this.summary,
  });

  final int index;
  final Map data;
  final bool summary;

  @override
  Widget build(BuildContext context) {
    final type = _clean(
      '${data['error_type'] ?? '未知类型'}',
    ).replaceAll('_', ' ').trim();
    final frequency = _valueText('frequency', data['frequency']);
    final rate = _valueText('success_rate', data['success_rate']);
    final message = _clean('${data['error_message'] ?? ''}').trim();
    final fix = _clean(
      '${data['fix_description'] ?? ''}',
    ).replaceFirst(RegExp(r'^修复[:：]\s*'), '').trim();
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('#$index $type · $frequency 次 · 修复成功率 $rate'),
          if (message.isNotEmpty)
            summary
                ? Text(
                    _summaryOf(message),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: _secondary(context),
                  )
                : Text(message, style: _secondary(context)),
          if (!summary && fix.isNotEmpty && fix != message)
            Text('处理方式：$fix', style: _secondary(context)),
        ],
      ),
    );
  }
}

class _StatsCard extends StatelessWidget {
  const _StatsCard({
    required this.icon,
    required this.title,
    required this.children,
  });

  final IconData icon;
  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: colors.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 18, color: colors.primary),
                const SizedBox(width: 6),
                Text(
                  title,
                  style: Theme.of(
                    context,
                  ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                ),
              ],
            ),
            const SizedBox(height: 10),
            ...children,
          ],
        ),
      ),
    );
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile(this.label, this.value);
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      width: 128,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: colors.surfaceContainerHighest.withValues(alpha: 0.4),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 11, color: Colors.grey),
          ),
          const SizedBox(height: 2),
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}

class _MetricRow extends StatelessWidget {
  const _MetricRow(this.label, this.value);
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 136, child: Text(label, style: _secondary(context))),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}

Widget _metricWrap(Map<String, Object?> data, List<String> order) {
  final tiles = _metricTiles(data, order);
  return tiles.isEmpty
      ? _emptyRow('暂无数据')
      : Wrap(spacing: 8, runSpacing: 8, children: tiles);
}

Widget _emptyRow(String text) =>
    Text(text, style: const TextStyle(fontSize: 12, color: Colors.grey));

Widget _subTitle(String text) =>
    Text(text, style: const TextStyle(fontSize: 12, color: Colors.grey));

TextStyle? _secondary(BuildContext context) => Theme.of(context)
    .textTheme
    .bodySmall
    ?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant);

Map<String, Object?> _asMap(Object? value) {
  if (value is Map) {
    return {for (final entry in value.entries) '${entry.key}': entry.value};
  }
  return <String, Object?>{};
}

List<Widget> _metricTiles(Map<String, Object?> data, List<String> order) {
  final keys = <String>[
    ...order.where(data.containsKey),
    ...data.keys.where((key) => !order.contains(key)),
  ];
  return [
    for (final key in keys)
      _MetricTile(_label(key), _valueText(key, data[key])),
  ];
}

const _labels = <String, String>{
  'total_tokens': '总 Token',
  'prompt_tokens': '输入 Token',
  'completion_tokens': '输出 Token',
  'total_messages': '消息数',
  'today_tokens': '今日 Token',
  'this_month_tokens': '本月 Token',
  'total_requests': '请求数',
  'cache_hits': '命中次数',
  'cache_misses': '未命中次数',
  'hit_rate': '命中率',
  'cached_entries': '缓存条目',
  'cache_size_mb': '缓存体积',
  'vector_index_size': '向量索引',
  'tech_index_groups': '技术索引分组',
  'learned_patterns': '已学习模式',
  'total_fixes_recorded': '累计修复记录',
  'total_sessions': '会话数',
  'overall_success_rate': '修复成功率',
  'free': '免费版',
  'basic': '基础版',
  'premium': '高级版',
  'enterprise': '企业版',
};

String _label(String key) => _labels[key] ?? key.replaceAll('_', ' ');

num? _asNumber(Object? value) {
  if (value is num) return value;
  if (value is String) return num.tryParse(value);
  return null;
}

String _valueText(String key, Object? value) {
  if (value == null) return '—';
  final number = _asNumber(value);
  if (number != null) {
    if (key.contains('rate')) return '${(number * 100).toStringAsFixed(1)}%';
    if (key.endsWith('_mb')) return '${number.toStringAsFixed(1)} MB';
    return _group(number);
  }
  if (value is Map) {
    if (value.isEmpty) return '—';
    return _clip(
      value.entries
          .map(
            (entry) =>
                '${_label('${entry.key}')} ${_valueText('${entry.key}', entry.value)}',
          )
          .join(' · '),
    );
  }
  if (value is List) return '${value.length} 项';
  if (value is bool) return value ? '是' : '否';
  return _clip(_clean('$value'));
}

String _group(num value) {
  final rounded = value.round();
  final negative = rounded < 0;
  final digits = rounded.abs().toString();
  final buffer = StringBuffer();
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) buffer.write(',');
    buffer.write(digits[i]);
  }
  return '${negative ? '-' : ''}$buffer';
}

String _clip(String text) =>
    text.length <= 160 ? text : '${text.substring(0, 160)}…';

/// 摘要行把换行压成单行，避免多行错误只展示第一行。
String _summaryOf(String text) {
  final oneLine = text.replaceAll(RegExp(r'\s*\n+\s*'), ' · ').trim();
  return oneLine.length <= 80 ? oneLine : '${oneLine.substring(0, 80)}…';
}

/// 后端部分历史记录把换行存成 HTML 实体，展示前还原成可读文本。
String _clean(String text) => text
    .replaceAll('&amp;', '&')
    .replaceAll('&lt;', '<')
    .replaceAll('&gt;', '>')
    .replaceAll('&quot;', '"')
    .replaceAll('&#39;', "'")
    .replaceAll('&#x27;', "'")
    .replaceAll('&nbsp;', ' ')
    .replaceAll('&#10;', '\n')
    .replaceAll('&#13;', '')
    .replaceAll('\r\n', '\n');
