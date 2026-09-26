import 'dart:convert';

import 'package:codingmatrix_desktop/infrastructure/agent/agent_stream_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/credential_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  // Regression guard: this test only uses the pre-existing default parameters,
  // so before the fix it compiles and fails on the missing `enable_skills`.
  test('编排请求默认发送全部七个生成开关', () async {
    final store = CredentialStore();
    final token = store.storeAccessToken('test-access');
    Map<String, dynamic>? body;
    final client = AgentStreamClient(
      baseUrl: 'https://example.com',
      httpClient: MockClient.streaming((request, bodyStream) async {
        body =
            jsonDecode(await bodyStream.bytesToString())
                as Map<String, dynamic>;
        return http.StreamedResponse(const Stream<List<int>>.empty(), 200);
      }),
      credentialStore: store,
    );

    await client.open(accessTokenRef: token, requirement: '做一个应用');

    expect(body, isNotNull);
    const expected = <String, bool>{
      'enable_review': true,
      'enable_validation': true,
      'enable_error_recovery': true,
      'enable_memory': true,
      'enable_skills': true,
      'spec_first': true,
      'dependency_graph': true,
    };
    for (final entry in expected.entries) {
      expect(body![entry.key], entry.value, reason: '${entry.key} 必须随请求发送');
    }
  });
}
