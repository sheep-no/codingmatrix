import 'dart:async';
import 'dart:convert';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/application/workbench_controller.dart';
import 'package:codingmatrix_desktop/domain/models/auth_session.dart';
import 'package:codingmatrix_desktop/domain/models/unified_models.dart';
import 'package:codingmatrix_desktop/infrastructure/agent/agent_stream_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/cloud_auth_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/credential_store.dart';
import 'package:codingmatrix_desktop/infrastructure/settings/capability_preferences.dart';
import 'package:codingmatrix_desktop/presentation/workbench_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'agent_delivery_test.dart' show DeliveryApi;
import 'generation_flags_controller_test.dart' show MemoryCapabilityPreferences;

AuthController _signedIn(CredentialStore store, String tokenRef) {
  return AuthController(
    CloudAuthClient(
      baseUrl: 'https://example.com',
      httpClient: MockClient((_) async => http.Response('', 500)),
      credentialStore: store,
    ),
    store,
    session: AuthSession(
      username: 'alice',
      permissionLevel: 'normal',
      accessTokenRef: tokenRef,
    ),
  );
}

Widget _app({
  required CredentialStore store,
  required String tokenRef,
  required WorkbenchController workbench,
  required CapabilityPreferences preferences,
}) {
  return ProviderScope(
    overrides: [
      authControllerProvider.overrideWith((_) => _signedIn(store, tokenRef)),
      workbenchControllerProvider.overrideWith((_) => workbench),
      authenticatedClientProvider.overrideWithValue(
        DeliveryApi((_, __, ___) async => <String, Object?>{}),
      ),
      capabilityPreferencesProvider.overrideWithValue(preferences),
    ],
    child: const MaterialApp(home: WorkbenchPage()),
  );
}

void main() {
  testWidgets('关闭 Skills 开关后请求不再启用 skills', (tester) async {
    final store = CredentialStore();
    final token = store.storeAccessToken('test-access');
    final bodies = <Map<String, dynamic>>[];
    final workbench = WorkbenchController(
      streamClient: AgentStreamClient(
        baseUrl: 'https://example.com',
        httpClient: MockClient.streaming((request, bodyStream) async {
          bodies.add(
            jsonDecode(await bodyStream.bytesToString())
                as Map<String, dynamic>,
          );
          return http.StreamedResponse(const Stream<List<int>>.empty(), 200);
        }),
        credentialStore: store,
      ),
    );
    await tester.pumpWidget(
      _app(
        store: store,
        tokenRef: token,
        workbench: workbench,
        preferences: MemoryCapabilityPreferences(),
      ),
    );
    await tester.pump();

    await tester.ensureVisible(find.byKey(const Key('generationFlag_skills')));
    await tester.tap(find.byKey(const Key('generationFlag_skills')));
    await tester.pump();

    await tester.enterText(find.byKey(const Key('requirementField')), '做一个应用');
    await tester.tap(find.byKey(const Key('startGenerationButton')));
    await tester.pump();
    await tester.pump();

    expect(bodies, hasLength(1));
    expect(bodies.single['enable_skills'], isFalse);
    expect(bodies.single['enable_review'], isTrue);
    expect(bodies.single['enable_memory'], isTrue);
  });

  testWidgets('生成进行中修改开关不改变已发出的请求体', (tester) async {
    final store = CredentialStore();
    final token = store.storeAccessToken('test-access');
    final source = StreamController<List<int>>();
    addTearDown(() {
      unawaited(source.close());
    });
    final bodies = <Map<String, dynamic>>[];
    final workbench = WorkbenchController(
      streamClient: AgentStreamClient(
        baseUrl: 'https://example.com',
        httpClient: MockClient.streaming((request, bodyStream) async {
          bodies.add(
            jsonDecode(await bodyStream.bytesToString())
                as Map<String, dynamic>,
          );
          return http.StreamedResponse(source.stream, 200);
        }),
        credentialStore: store,
      ),
    );
    await tester.pumpWidget(
      _app(
        store: store,
        tokenRef: token,
        workbench: workbench,
        preferences: MemoryCapabilityPreferences(),
      ),
    );
    await tester.pump();

    await tester.enterText(find.byKey(const Key('requirementField')), '做一个应用');
    await tester.tap(find.byKey(const Key('startGenerationButton')));
    await tester.pump();
    await tester.pump();
    expect(bodies.single['enable_skills'], isTrue);

    await tester.ensureVisible(find.byKey(const Key('generationFlag_skills')));
    await tester.tap(find.byKey(const Key('generationFlag_skills')));
    await tester.pump();

    expect(bodies, hasLength(1));
    expect(bodies.single['enable_skills'], isTrue);
  });

  testWidgets('首次生成按新建请求发送', (tester) async {
    final store = CredentialStore();
    final token = store.storeAccessToken('test-access');
    final bodies = <Map<String, dynamic>>[];
    final workbench = WorkbenchController(
      streamClient: AgentStreamClient(
        baseUrl: 'https://example.com',
        httpClient: MockClient.streaming((request, bodyStream) async {
          bodies.add(
            jsonDecode(await bodyStream.bytesToString())
                as Map<String, dynamic>,
          );
          return http.StreamedResponse(const Stream<List<int>>.empty(), 200);
        }),
        credentialStore: store,
      ),
    );
    await tester.pumpWidget(
      _app(
        store: store,
        tokenRef: token,
        workbench: workbench,
        preferences: MemoryCapabilityPreferences(),
      ),
    );
    await tester.pump();

    await tester.enterText(find.byKey(const Key('requirementField')), '做一个应用');
    await tester.tap(find.byKey(const Key('startGenerationButton')));
    await tester.pump();
    await tester.pump();

    expect(bodies, hasLength(1));
    expect(bodies.single['incremental'], isFalse);
    expect(bodies.single.containsKey('engine'), isFalse);
    expect(bodies.single.containsKey('project_path'), isFalse);
  });

  testWidgets('已有生成结果时改为发送增量修改请求', (tester) async {
    final store = CredentialStore();
    final token = store.storeAccessToken('test-access');
    final bodies = <Map<String, dynamic>>[];
    final workbench = WorkbenchController(
      streamClient: AgentStreamClient(
        baseUrl: 'https://example.com',
        httpClient: MockClient.streaming((request, bodyStream) async {
          bodies.add(
            jsonDecode(await bodyStream.bytesToString())
                as Map<String, dynamic>,
          );
          return http.StreamedResponse(const Stream<List<int>>.empty(), 200);
        }),
        credentialStore: store,
      ),
    );
    // A finished run left a project behind, so the next requirement modifies it.
    workbench.bindTask(
      const Task(
        taskId: 'done-1',
        status: 'success',
        resultJson: <String, dynamic>{'project_path': '1/1789218793436'},
      ),
    );
    await tester.pumpWidget(
      _app(
        store: store,
        tokenRef: token,
        workbench: workbench,
        preferences: MemoryCapabilityPreferences(),
      ),
    );
    await tester.pump();

    await tester.enterText(
      find.byKey(const Key('requirementField')),
      '加一个退出按钮',
    );
    await tester.tap(find.byKey(const Key('startGenerationButton')));
    await tester.pump();
    await tester.pump();

    expect(bodies, hasLength(1));
    expect(bodies.single['incremental'], isTrue);
    expect(bodies.single['engine'], 'core');
    expect(bodies.single['project_path'], '1/1789218793436');
  });

  testWidgets('输入项目名后随生成请求发送', (tester) async {
    final store = CredentialStore();
    final token = store.storeAccessToken('test-access');
    final bodies = <Map<String, dynamic>>[];
    final workbench = WorkbenchController(
      streamClient: AgentStreamClient(
        baseUrl: 'https://example.com',
        httpClient: MockClient.streaming((request, bodyStream) async {
          bodies.add(
            jsonDecode(await bodyStream.bytesToString())
                as Map<String, dynamic>,
          );
          return http.StreamedResponse(const Stream<List<int>>.empty(), 200);
        }),
        credentialStore: store,
      ),
    );
    await tester.pumpWidget(
      _app(
        store: store,
        tokenRef: token,
        workbench: workbench,
        preferences: MemoryCapabilityPreferences(),
      ),
    );
    await tester.pump();

    await tester.enterText(find.byKey(const Key('requirementField')), '做一个应用');
    await tester.enterText(
      find.byKey(const Key('projectNameField')),
      'my_flutter_app',
    );
    await tester.tap(find.byKey(const Key('startGenerationButton')));
    await tester.pump();
    await tester.pump();

    expect(bodies, hasLength(1));
    expect(bodies.single['project_name'], 'my_flutter_app');
  });

  testWidgets('停止清理后的任务不再按增量修改发送', (tester) async {
    final store = CredentialStore();
    final token = store.storeAccessToken('test-access');
    final bodies = <Map<String, dynamic>>[];
    final workbench = WorkbenchController(
      streamClient: AgentStreamClient(
        baseUrl: 'https://example.com',
        httpClient: MockClient.streaming((request, bodyStream) async {
          bodies.add(
            jsonDecode(await bodyStream.bytesToString())
                as Map<String, dynamic>,
          );
          return http.StreamedResponse(const Stream<List<int>>.empty(), 200);
        }),
        credentialStore: store,
      ),
    );
    // Stop and clean keeps the task, but the project files are gone.
    workbench.bindTask(
      const Task(
        taskId: 'stopped-1',
        status: 'cancelled',
        resultJson: <String, dynamic>{'project_path': '1/1789218793436'},
      ),
    );
    await tester.pumpWidget(
      _app(
        store: store,
        tokenRef: token,
        workbench: workbench,
        preferences: MemoryCapabilityPreferences(),
      ),
    );
    await tester.pump();

    await tester.enterText(
      find.byKey(const Key('requirementField')),
      '重新做一个应用',
    );
    await tester.tap(find.byKey(const Key('startGenerationButton')));
    await tester.pump();
    await tester.pump();

    expect(bodies, hasLength(1));
    expect(bodies.single['incremental'], isFalse);
    expect(bodies.single.containsKey('project_path'), isFalse);
  });
}
