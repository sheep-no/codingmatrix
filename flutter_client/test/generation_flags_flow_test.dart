import 'dart:async';
import 'dart:convert';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/application/workbench_controller.dart';
import 'package:codingmatrix_desktop/domain/models/auth_session.dart';
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
}
