import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/application/image_generation_controller.dart';
import 'package:codingmatrix_desktop/application/workflow_controller.dart';
import 'package:codingmatrix_desktop/application/github_controller.dart';
import 'package:codingmatrix_desktop/domain/models/auth_session.dart';
import 'package:codingmatrix_desktop/domain/models/image_generation.dart';
import 'package:codingmatrix_desktop/presentation/github_settings_page.dart';
import 'package:codingmatrix_desktop/presentation/workbench_page.dart';
import 'agent_delivery_test.dart' show DeliveryApi;
import 'auth_session_test.dart' show Fixture;
import 'image_generation_test.dart' show key, pixel;

class ModuleAuth extends AuthController {
  ModuleAuth(Fixture fixture) : super(fixture.auth, fixture.store);
  void switchAccount(String id) {
    state = AuthState(
      session: AuthSession(
        username: id,
        permissionLevel: 'normal',
        accessTokenRef: id,
      ),
    );
  }
}

void main() {
  testWidgets('320px workbench opens all three modules from menu', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authControllerProvider.overrideWith(
            (_) => ModuleAuth(Fixture())..switchAccount('alice'),
          ),
          authenticatedClientProvider.overrideWithValue(
            DeliveryApi((_, __, ___) async => {}),
          ),
        ],
        child: const MaterialApp(home: WorkbenchPage()),
      ),
    );
    await tester.pumpAndSettle();
    for (final title in ['图片生成', '工作流执行', 'GitHub 设置']) {
      await tester.tap(find.byTooltip('更多模块'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(PopupMenuItem<String>, title));
      await tester.pumpAndSettle();
      expect(find.widgetWithText(AppBar, title), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pageBack();
      await tester.pumpAndSettle();
    }
  });
  test(
    'account change recreates all module states and ignores pending image result',
    () async {
      final auth = ModuleAuth(Fixture())..switchAccount('alice');
      final pending = Completer<Object?>();
      final container = ProviderContainer(
        overrides: [
          authControllerProvider.overrideWith((_) => auth),
          authenticatedClientProvider.overrideWithValue(
            DeliveryApi((_, __, ___) => pending.future),
          ),
        ],
      );
      addTearDown(container.dispose);
      final image = container.listen(
        imageGenerationControllerProvider,
        (_, __) {},
      );
      final workflow = container.listen(workflowControllerProvider, (_, __) {});
      final github = container.listen(githubControllerProvider, (_, __) {});
      final oldImage = container.read(
        imageGenerationControllerProvider.notifier,
      );
      final oldWorkflow = container.read(workflowControllerProvider.notifier);
      final oldGithub = container.read(githubControllerProvider.notifier);
      final run = oldImage.generate(
        const ImageGenerationInput(prompt: 'private'),
        key,
      );
      auth.switchAccount('bob');
      expect(image.read().images, isEmpty);
      expect(image.read().busy, false);
      expect(workflow.read().snapshot.id, isNull);
      expect(github.read().binding, isNull);
      expect(
        identical(
          oldWorkflow,
          container.read(workflowControllerProvider.notifier),
        ),
        false,
      );
      expect(
        identical(oldGithub, container.read(githubControllerProvider.notifier)),
        false,
      );
      pending.complete({
        'success': true,
        'images': [pixel],
      });
      await run;
      expect(image.read().images, isEmpty);
    },
  );

  testWidgets(
    'account switch clears GitHub draft and discards late old configuration',
    (tester) async {
      final auth = ModuleAuth(Fixture())..switchAccount('alice');
      final pending = Completer<Object?>();
      var loads = 0;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authControllerProvider.overrideWith((_) => auth),
            authenticatedClientProvider.overrideWithValue(
              DeliveryApi((_, __, ___) {
                loads++;
                return loads == 1
                    ? pending.future
                    : Future.value({
                        'username': 'bob',
                        'persisted': true,
                        'has_token': false,
                        'credential_state': 'missing',
                        'use_github': false,
                      });
              }),
            ),
          ],
          child: const MaterialApp(home: GithubSettingsPage()),
        ),
      );
      await tester.pump();
      auth.switchAccount('bob');
      await tester.pumpAndSettle();
      pending.complete({'username': 'alice', 'persisted': true});
      await tester.pumpAndSettle();
      final username = tester.widget<TextField>(
        find.byKey(const Key('githubUsername')),
      );
      expect(username.controller!.text, 'bob');
      await tester.enterText(
        find.byKey(const Key('githubToken')),
        'draft-secret',
      );
      auth.switchAccount('carol');
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<TextField>(find.byKey(const Key('githubToken')))
            .controller!
            .text,
        isEmpty,
      );
      await tester.pumpWidget(const SizedBox());
      expect(tester.takeException(), isNull);
    },
  );
}
