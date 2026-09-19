import 'package:codingmatrix_desktop/infrastructure/auth/authenticated_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/cloud_auth_client.dart';
import 'package:flutter_test/flutter_test.dart';

import 'auth_session_test.dart' show Fixture;
import 'stream_timeout_test.dart' show SilentServer;

void main() {
  test('流式响应在空闲超过流式超时后中断', () async {
    final fixture = Fixture(timeout: const Duration(milliseconds: 60));
    await fixture.login();
    final server = SilentServer();
    final api = AuthenticatedClient(
      fixture.auth,
      server.client,
      streamTimeout: const Duration(milliseconds: 60),
    );

    final stream = await api.sendJsonStream('/api/v1/chat', {
      'prompt': '做一个应用',
    });
    await expectLater(
      stream.toList(),
      throwsA(
        isA<CloudAuthException>().having(
          (error) => error.message,
          'message',
          '响应连接中断，请确认任务状态后手动恢复',
        ),
      ),
    );
  });
}
