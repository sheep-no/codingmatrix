import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/infrastructure/errors/failure_text.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('HTTP 状态映射为可读根因并保留状态码', () {
    expect(httpFailureText(404), '接口不存在或资源已被删除，请核对服务地址与版本（HTTP 404）');
    expect(httpFailureText(409), contains('任务状态冲突'));
    expect(httpFailureText(429), contains('请求过于频繁'));
    expect(httpFailureText(500), contains('模型服务未配置'));
    expect(httpFailureText(502), contains('上游服务不可用'));
    expect(httpFailureText(503), contains('服务暂不可用'));
    expect(httpFailureText(507), contains('磁盘空间不足'));
    expect(httpFailureText(418), contains('HTTP 418'));
  });

  test('未知 5xx 与未知 4xx 使用不同兜底文案', () {
    expect(httpFailureReason(599), '服务端异常，请稍后重试');
    expect(httpFailureReason(418), '请求失败');
  });

  test('错误体提取后端可操作原因', () {
    expect(
      serverFailureDetail('{"code":"INTERNAL_ERROR","message":"获取 Key 列表失败"}'),
      '获取 Key 列表失败',
    );
    expect(
      serverFailureDetail('{"detail":"磁盘空间不足（可用：0.78 GB）"}'),
      '磁盘空间不足（可用：0.78 GB）',
    );
    expect(serverFailureDetail('{"detail":[{"msg":"字段缺失"}]}'), isNull);
    // Plain text may echo secrets, so only the structured envelope is trusted.
    expect(serverFailureDetail('plain text failure'), isNull);
    expect(serverFailureDetail('<html>500</html>'), isNull);
    expect(serverFailureDetail('   '), isNull);
    expect(serverFailureDetail('{"message":"  "}'), isNull);
  });

  test('超长错误体被截断，避免撑破单行文案', () {
    final detail = serverFailureDetail('{"message":"${'x' * 500}"}');
    expect(detail, isNotNull);
    expect(detail!.length, 201);
    expect(detail.endsWith('…'), isTrue);
  });

  test('流式失败区分解压、超时、断网与格式错误', () {
    expect(
      streamFailureText(const FormatException('Filter error, bad data')),
      contains('响应解压失败'),
    );
    expect(streamFailureText(TimeoutException('slow')), contains('响应超时'));
    expect(
      streamFailureText(const SocketException('connection lost')),
      contains('网络连接中断'),
    );
    expect(
      streamFailureText(const FormatException('事件格式无效')),
      contains('响应内容格式异常'),
    );
    expect(streamFailureText(StateError('boom')), contains('boom'));
  });
}
