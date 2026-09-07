import 'package:codingmatrix_desktop/infrastructure/sse/sse_parser.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('parses incremental SSE frames split across chunks', () {
    final parser = SseParser();

    expect(
      parser.push('data: {"type":"log","data":{"message":"he'),
      isEmpty,
    );

    final events = parser.push('llo"}}\n\ndata: {"type":"heartbeat"}\n\n');
    expect(events, hasLength(2));
    expect(events[0].type, 'log');
    expect(events[0].data?['message'], 'hello');
    expect(events[1].type, 'heartbeat');
  });

  test('keeps incomplete trailing frame in the buffer', () {
    final parser = SseParser();
    parser.push('data: {"type":"progress","data":{"progress":40}}\n\n');
    parser.push('data: {"type":"done"');
    final completed = parser.push(',"data":{"ok":true}}\n\n');
    expect(completed.single.type, 'done');
    expect(completed.single.data?['ok'], true);
  });
}
