import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/domain/models/auth_session.dart';
import 'package:codingmatrix_desktop/presentation/mcp_admin_page.dart';
import 'package:codingmatrix_desktop/presentation/ppt_page.dart';
import 'package:codingmatrix_desktop/presentation/workbench_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'agent_delivery_test.dart' show DeliveryApi;
import 'auth_session_test.dart' show Fixture;

class ShellAuth extends AuthController {
  ShellAuth(Fixture fixture) : super(fixture.auth, fixture.store);

  void switchAccount(String id, {String level = 'normal'}) {
    state = AuthState(
      session: AuthSession(
        username: id,
        permissionLevel: level,
        accessTokenRef: id,
      ),
    );
  }
}

Widget shell(ShellAuth auth) {
  return ProviderScope(
    overrides: [
      authControllerProvider.overrideWith((_) => auth),
      authenticatedClientProvider.overrideWithValue(
        DeliveryApi((_, __, ___) async => <String, Object?>{}),
      ),
    ],
    child: const MaterialApp(home: WorkbenchPage()),
  );
}

void useSize(WidgetTester tester, Size size) {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

void main() {
  testWidgets('宽视口常驻展示分组导航', (tester) async {
    useSize(tester, const Size(1200, 900));
    await tester.pumpWidget(
      shell(ShellAuth(Fixture())..switchAccount('alice')),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('capabilityNav_agent')), findsOneWidget);
    expect(find.text('工作区'), findsOneWidget);
    expect(find.text('创作'), findsOneWidget);
    expect(find.text('数据'), findsOneWidget);
    expect(find.text('系统'), findsOneWidget);
    expect(find.byType(Drawer), findsNothing);
    expect(
      tester
          .widget<ListTile>(find.byKey(const Key('capabilityNav_agent')))
          .selected,
      isTrue,
    );
  });

  testWidgets('窄视口通过抽屉选择能力并关闭抽屉', (tester) async {
    useSize(tester, const Size(600, 900));
    await tester.pumpWidget(
      shell(ShellAuth(Fixture())..switchAccount('alice')),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('capabilityNav_agent')), findsNothing);
    await tester.tap(find.byIcon(Icons.menu));
    await tester.pumpAndSettle();
    expect(find.text('工作区'), findsOneWidget);

    await tester.ensureVisible(find.byKey(const Key('capabilityNav_chat')));
    await tester.tap(find.byKey(const Key('capabilityNav_chat')));
    await tester.pumpAndSettle();

    expect(find.byType(Drawer), findsNothing);
    expect(find.widgetWithText(AppBar, '聊天'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('权限过滤隐藏高权限能力', (tester) async {
    useSize(tester, const Size(1200, 900));
    final auth = ShellAuth(Fixture())
      ..switchAccount('root', level: 'superadmin');
    await tester.pumpWidget(shell(auth));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('capabilityNav_admin')), findsOneWidget);
    expect(find.byKey(const Key('capabilityNav_mcp')), findsOneWidget);

    auth.switchAccount('alice');
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('capabilityNav_admin')), findsNothing);
    expect(find.byKey(const Key('capabilityNav_mcp')), findsNothing);
  });

  testWidgets('权限下降关闭已打开的高权限能力', (tester) async {
    useSize(tester, const Size(1200, 900));
    final auth = ShellAuth(Fixture())
      ..switchAccount('root', level: 'superadmin');
    await tester.pumpWidget(shell(auth));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.byKey(const Key('capabilityNav_mcp')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('capabilityNav_mcp')));
    await tester.pumpAndSettle();
    expect(find.byType(McpAdminPage), findsOneWidget);

    auth.switchAccount('alice');
    await tester.pumpAndSettle();

    expect(find.byType(McpAdminPage), findsNothing);
    expect(
      tester
          .widget<ListTile>(find.byKey(const Key('capabilityNav_agent')))
          .selected,
      isTrue,
    );
  });

  testWidgets('账号切换清空已打开的能力页', (tester) async {
    useSize(tester, const Size(1200, 900));
    final auth = ShellAuth(Fixture())..switchAccount('alice');
    await tester.pumpWidget(shell(auth));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.byKey(const Key('capabilityNav_ppt')));
    await tester.tap(find.byKey(const Key('capabilityNav_ppt')));
    await tester.pumpAndSettle();
    expect(find.byType(PptPage), findsOneWidget);

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    expect(find.byType(PptPage), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('能力页嵌入外壳后只保留一层标题栏', (tester) async {
    useSize(tester, const Size(1200, 900));
    await tester.pumpWidget(
      shell(ShellAuth(Fixture())..switchAccount('alice')),
    );
    await tester.pumpAndSettle();
    expect(find.byType(AppBar), findsOneWidget);

    await tester.ensureVisible(find.byKey(const Key('capabilityNav_chat')));
    await tester.tap(find.byKey(const Key('capabilityNav_chat')));
    await tester.pumpAndSettle();

    expect(find.byType(AppBar), findsOneWidget);
    expect(find.widgetWithText(AppBar, '聊天'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
