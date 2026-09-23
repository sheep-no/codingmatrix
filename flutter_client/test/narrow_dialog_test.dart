import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/presentation/admin_page.dart';
import 'package:codingmatrix_desktop/presentation/agent_history_page.dart';
import 'package:codingmatrix_desktop/presentation/mcp_admin_page.dart';
import 'package:codingmatrix_desktop/presentation/workflow_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'agent_delivery_test.dart' show DeliveryApi;
import 'auth_session_test.dart' show Fixture;
import 'module_lifecycle_test.dart' show ModuleAuth;

const _userItem = {
  'id': 1,
  'username': 'alice',
  'email': 'alice@example.com',
  'permission_level': 'admin',
};

const _serverItem = {
  'name': 'filesystem',
  'transport': 'stdio',
  'description': '本地文件',
  'enabled': true,
};

typedef Handler = Future<Object?> Function(String path, String method);

/// A phone-sized surface (360x640 logical pixels).
void phone(WidgetTester tester) {
  tester.view.physicalSize = const Size(360, 640);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  addTearDown(tester.view.resetViewInsets);
}

Future<void> pumpPage(WidgetTester tester, Widget page, Handler handler) async {
  final auth = ModuleAuth(Fixture())..switchAccount('alice');
  final container = ProviderContainer(
    overrides: [
      authControllerProvider.overrideWith((_) => auth),
      authenticatedClientProvider.overrideWithValue(
        DeliveryApi((path, method, _) => handler(path, method)),
      ),
    ],
  );
  addTearDown(container.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: MaterialApp(home: page),
    ),
  );
  await tester.pump();
  await tester.pump();
}

/// Opens a dialog, raises the software keyboard, and reports the layout error
/// (if any) the dialog produced.
Future<Object?> openThenKeyboard(WidgetTester tester, Finder trigger) async {
  await tester.tap(trigger);
  await tester.pumpAndSettle();
  tester.view.viewInsets = const FakeViewPadding(bottom: 300);
  await tester.pumpAndSettle();
  return tester.takeException();
}

void expectNoLayoutError(Object? error, String label) {
  if (error != null) {
    fail('$label 在手机键盘下出现布局异常: $error');
  }
}

void main() {
  testWidgets('手机键盘弹出时管理员创建用户对话框不溢出', (tester) async {
    phone(tester);
    await pumpPage(
      tester,
      const AdminPage(),
      (_, __) async => {
        'total': 1,
        'users': [_userItem],
      },
    );

    final error = await openThenKeyboard(tester, find.text('创建用户'));
    expect(find.byType(TextField), findsNWidgets(3));
    expectNoLayoutError(error, '创建用户');
  });

  testWidgets('手机键盘弹出时管理员编辑用户对话框不溢出', (tester) async {
    phone(tester);
    await pumpPage(
      tester,
      const AdminPage(),
      (_, __) async => {
        'total': 1,
        'users': [_userItem],
      },
    );

    await tester.tap(find.text('用户管理'));
    await tester.pumpAndSettle();
    final error = await openThenKeyboard(tester, find.byIcon(Icons.edit));
    expect(find.text('编辑用户'), findsOneWidget);
    expectNoLayoutError(error, '编辑用户');
  });

  testWidgets('手机键盘弹出时管理员沙箱配置对话框不溢出', (tester) async {
    phone(tester);
    await pumpPage(
      tester,
      const AdminPage(),
      (_, __) async => {'sandbox_enabled': true, 'max_memory_mb': 512},
    );

    final error = await openThenKeyboard(tester, find.text('沙箱配置'));
    expectNoLayoutError(error, '沙箱配置');
  });

  testWidgets('手机键盘弹出时工作流导入对话框不溢出', (tester) async {
    phone(tester);
    await pumpPage(tester, const WorkflowPage(), (_, __) async => null);

    final error = await openThenKeyboard(tester, find.text('导入工作流'));
    expect(find.text('导入工作流 JSON'), findsOneWidget);
    expectNoLayoutError(error, '工作流导入');
  });

  testWidgets('手机键盘弹出时 MCP 编辑对话框不溢出', (tester) async {
    phone(tester);
    await pumpPage(
      tester,
      const McpAdminPage(),
      (_, __) async => {
        'servers': [_serverItem],
      },
    );

    final error = await openThenKeyboard(tester, find.byIcon(Icons.edit));
    expect(find.byType(TextField), findsWidgets);
    expectNoLayoutError(error, 'MCP 编辑');
  });

  testWidgets('手机键盘弹出时会话历史并发限制对话框不溢出', (tester) async {
    phone(tester);
    await pumpPage(
      tester,
      const AgentHistoryPage(),
      (_, __) async => {'sessions': <Object?>[]},
    );

    final error = await openThenKeyboard(tester, find.byIcon(Icons.tune));
    expect(find.text('调整并发限制'), findsOneWidget);
    expect(find.byType(TextField), findsNWidgets(2));
    expectNoLayoutError(error, '并发限制');
  });

  testWidgets('手机宽度下 MCP 长连接测试结果对话框不溢出', (tester) async {
    phone(tester);
    await pumpPage(tester, const McpAdminPage(), (path, __) async {
      if (path.endsWith('/test')) {
        return {
          'ok': true,
          'logs': List<String>.generate(60, (i) => '第 $i 行连接测试输出'),
        };
      }
      return {
        'servers': [_serverItem],
      };
    });

    await tester.tap(find.byIcon(Icons.network_check));
    await tester.pumpAndSettle();
    expect(find.textContaining('连接测试'), findsWidgets);
    expectNoLayoutError(tester.takeException(), 'MCP 连接测试结果');

    // 不溢出还不够：内容必须真的能滚动看到，否则结果被裁掉但测试仍然通过。
    final scrollable = find.descendant(
      of: find.byType(AlertDialog),
      matching: find.byType(Scrollable),
    );
    expect(scrollable, findsWidgets);
    final position = tester.state<ScrollableState>(scrollable.first).position;
    expect(position.maxScrollExtent, greaterThan(0));
  });
}
