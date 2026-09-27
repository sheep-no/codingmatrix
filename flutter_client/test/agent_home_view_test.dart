import 'dart:convert';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/application/workbench_controller.dart';
import 'package:codingmatrix_desktop/domain/models/auth_session.dart';
import 'package:codingmatrix_desktop/domain/models/unified_models.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/cloud_auth_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/credential_store.dart';
import 'package:codingmatrix_desktop/presentation/agent_decision_page.dart';
import 'package:codingmatrix_desktop/presentation/workbench_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

// The workbench shell opens the `agent` capability first, so pumping
// WorkbenchPage renders AgentHomeView by default.
import 'agent_delivery_test.dart' show question;

AuthController _signedInAuth(CredentialStore store) {
  return AuthController(
    CloudAuthClient(
      baseUrl: 'https://example.com',
      httpClient: MockClient((_) async => http.Response('', 500)),
      credentialStore: store,
    ),
    store,
    session: const AuthSession(
      username: 'alice',
      permissionLevel: 'normal',
      accessTokenRef: 'ref',
    ),
  );
}

Future<void> _pumpHome(
  WidgetTester tester,
  WorkbenchController workbench,
) async {
  final store = CredentialStore();
  final container = ProviderContainer(
    overrides: [
      authControllerProvider.overrideWith((_) => _signedInAuth(store)),
      workbenchControllerProvider.overrideWith((_) => workbench),
    ],
  );
  addTearDown(container.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: WorkbenchPage()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('有待决策时展示入口并可进入决策页', (tester) async {
    final workbench = WorkbenchController();
    workbench.bindTask(
      const Task(taskId: 't1', sessionId: 's1', status: 'awaitingDecision'),
    );
    workbench.ingestSseChunk(
      'data: ${jsonEncode({
        'type': 'critical_decisions',
        'data': {
          'decisions': [question],
        },
      })}\n\n',
    );
    expect(workbench.state.decisions, isNotEmpty);

    await _pumpHome(tester, workbench);
    expect(find.text('处理架构决策'), findsOneWidget);

    await tester.tap(find.text('处理架构决策'));
    await tester.pumpAndSettle();
    expect(find.byType(AgentDecisionPage), findsOneWidget);
  });

  testWidgets('没有待决策时不展示决策入口', (tester) async {
    final workbench = WorkbenchController();
    workbench.bindTask(
      const Task(taskId: 't1', sessionId: 's1', status: 'running'),
    );

    await _pumpHome(tester, workbench);
    expect(find.text('处理架构决策'), findsNothing);
  });

  testWidgets('有项目产物时展示查看入口', (tester) async {
    final workbench = WorkbenchController();
    workbench.bindTask(
      const Task(
        taskId: 't1',
        sessionId: 's1',
        status: 'success',
        resultJson: {'project_path': '1/demo'},
      ),
    );

    await _pumpHome(tester, workbench);
    expect(find.text('查看项目文件'), findsOneWidget);
  });

  testWidgets('没有项目产物时不展示查看入口', (tester) async {
    final workbench = WorkbenchController();
    workbench.bindTask(
      const Task(taskId: 't1', sessionId: 's1', status: 'success'),
    );

    await _pumpHome(tester, workbench);
    expect(find.text('查看项目文件'), findsNothing);
  });

  testWidgets('超长事件正文被截断而不是整体渲染', (tester) async {
    final workbench = WorkbenchController();
    workbench.bindTask(
      const Task(taskId: 't1', sessionId: 's1', status: 'running'),
    );
    const marker = 'TAIL_MARKER_MUST_NOT_RENDER';
    final frame = jsonEncode({
      'type': 'log',
      'data': {'message': 'x' * 2600 + marker},
    });
    workbench.ingestSseChunk('data: $frame\n\n');

    await _pumpHome(tester, workbench);
    expect(find.textContaining('（已截断'), findsOneWidget);
    expect(find.textContaining(marker), findsNothing);
  });
}
