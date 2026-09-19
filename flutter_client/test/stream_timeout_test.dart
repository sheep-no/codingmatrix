import 'dart:async';
import 'dart:convert';

import 'package:codingmatrix_desktop/infrastructure/auth/authenticated_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'auth_session_test.dart' show Fixture;

/// Drives one silent stream per request. A real chat stream stays silent while
/// the server prepares context or waits for the first model token.
class SilentServer {
  final bodies = <StreamController<List<int>>>[];

  MockClient get client => MockClient.streaming((request, bodyStream) async {
    final body = StreamController<List<int>>();
    bodies.add(body);
    return http.StreamedResponse(body.stream, 200);
  });

  StreamController<List<int>> get only => bodies.single;
}

void main() {
  test('流式响应在普通请求超时后仍保持连接', () async {
    // The request timeout is far shorter than the stream's silence, which is
    // what a long context-preparation phase looks like on the wire. With the
    // request timeout reused for the body this stream would be cut off before
    // the server sent its first event.
    final fixture = Fixture(timeout: const Duration(milliseconds: 60));
    await fixture.login();
    final server = SilentServer();
    final api = AuthenticatedClient(fixture.auth, server.client);

    final stream = await api.sendJsonStream('/api/v1/chat', {
      'prompt': '做一个应用',
    });
    final collected = stream.toList();
    await Future<void>.delayed(const Duration(milliseconds: 150));
    server.only.add(utf8.encode('data: {"response":"hi"}\n'));
    await server.only.close();
    final chunks = await collected;

    expect(
      utf8.decode(chunks.expand((chunk) => chunk).toList()),
      contains('hi'),
    );
  });
}
