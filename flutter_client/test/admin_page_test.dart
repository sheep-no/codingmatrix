import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/presentation/admin_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'agent_delivery_test.dart' show DeliveryApi;
import 'auth_session_test.dart' show Fixture;
import 'module_lifecycle_test.dart' show ModuleAuth;

const userItem = {
  'id': 1,
  'username': 'alice',
  'email': 'alice@example.com',
  'permission_level': 'admin',
};

const usersPayload = {
  'total': 1,
  'users': [userItem],
};

void main() {
  testWidgets('进入页面不自动拉取用户', (tester) async {
    var calls = 0;
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((_, __, ___) async {
            calls++;
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.pump();
    expect(calls, 0);
    expect(find.text('alice'), findsNothing);
    expect(find.text('用户管理'), findsOneWidget);
  });

  testWidgets('点击用户管理后显示用户列表', (tester) async {
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            expect(path, '/api/v2/Controller/users?page=1&page_size=50');
            expect(method, 'GET');
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('用户管理'));
    await tester.pump();
    await tester.pump();
    expect(find.text('用户总数：1'), findsOneWidget);
    expect(find.text('alice'), findsOneWidget);
    expect(find.textContaining('alice@example.com'), findsOneWidget);
  });

  testWidgets('切换账号清空上一个账号的用户列表且不自动拉取', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    var calls = 0;
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((_, __, ___) async {
            calls++;
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('用户管理'));
    await tester.pump();
    await tester.pump();
    expect(find.text('alice'), findsOneWidget);
    expect(calls, 1);

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    expect(find.text('alice'), findsNothing);
    expect(find.textContaining('用户总数'), findsNothing);
    expect(calls, 1);
    expect(tester.takeException(), isNull);
  });

  testWidgets('切换账号关闭已打开的用户编辑弹层', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((_, __, ___) async => usersPayload),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('用户管理'));
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byTooltip('编辑'));
    await tester.pump();
    await tester.pump();
    expect(find.byType(AlertDialog), findsOneWidget);
    expect(find.text('编辑用户'), findsOneWidget);

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    expect(find.byType(AlertDialog), findsNothing);
    expect(find.text('编辑用户'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('加载中网络断开显示错误', (tester) async {
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi(
            (_, __, ___) async =>
                throw const SocketException('connection lost'),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('用户管理'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('用户列表读取失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('alice'), findsNothing);
  });

  testWidgets('加载中退出再进入需再次点击拉取', (tester) async {
    var calls = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((_, __, ___) async {
            calls++;
            if (calls == 1) return pending.future;
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('用户管理'));
    await tester.pump();
    expect(find.byType(LinearProgressIndicator), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开管理后台'))),
      ),
    );
    await tester.pump();
    pending.complete({
      'total': 1,
      'users': [
        {
          'id': 9,
          'username': '旧用户',
          'email': 'old@example.com',
          'permission_level': 'normal',
        },
      ],
    });
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.pump();
    expect(find.text('旧用户'), findsNothing);
    expect(find.text('alice'), findsNothing);
    expect(calls, 1);

    await tester.tap(find.text('用户管理'));
    await tester.pump();
    await tester.pump();
    expect(find.text('alice'), findsOneWidget);
    expect(find.text('旧用户'), findsNothing);
    expect(calls, 2);
  });

  testWidgets('创建用户网络断开显示失败原文', (tester) async {
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            if (path.contains('create_user')) {
              expect(method, 'POST');
              expect(body, {
                'username': 'bob',
                'email': 'bob@example.com',
                'password': 'secret',
              });
              throw const SocketException('connection lost');
            }
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('创建用户'));
    await tester.pump();
    await tester.enterText(find.byType(TextField).at(0), 'bob');
    await tester.enterText(find.byType(TextField).at(1), 'bob@example.com');
    await tester.enterText(find.byType(TextField).at(2), 'secret');
    await tester.tap(find.text('创建'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('用户创建失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('alice'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('创建中退出再进入会丢掉错误', (tester) async {
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, _, __) async {
            if (path.contains('create_user')) return pending.future;
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('创建用户'));
    await tester.pump();
    await tester.enterText(find.byType(TextField).at(0), 'bob');
    await tester.enterText(find.byType(TextField).at(1), 'bob@example.com');
    await tester.enterText(find.byType(TextField).at(2), 'secret');
    await tester.tap(find.text('创建'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开管理后台'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.pump();
    expect(find.textContaining('用户创建失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('alice'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('删除用户网络断开显示失败原文', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('delete_user')) {
              expect(path, '/api/v2/Controller/delete_user/1');
              expect(method, 'DELETE');
              throw const SocketException('connection lost');
            }
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('用户管理'));
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('删除'));
    await tester.tap(find.byTooltip('删除'));
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, '删除'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('用户删除失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('alice'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('删除中退出再进入会丢掉错误', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('delete_user')) return pending.future;
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('用户管理'));
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('删除'));
    await tester.tap(find.byTooltip('删除'));
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, '删除'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开管理后台'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.pump();
    expect(find.textContaining('用户删除失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('alice'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('编辑中退出再进入会丢掉错误', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('update_user')) return pending.future;
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('用户管理'));
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('编辑'));
    await tester.tap(find.byTooltip('编辑'));
    await tester.pump();
    await tester.tap(find.text('保存'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开管理后台'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.pump();
    expect(find.textContaining('用户更新失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('alice'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('编辑用户网络断开显示失败原文', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            if (path.contains('update_user')) {
              expect(path, '/api/v2/Controller/update_user/1');
              expect(method, 'PATCH');
              expect(body, {
                'username': 'alice',
                'email': 'alice@example.com',
                'permission_level': 'admin',
              });
              throw const SocketException('connection lost');
            }
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('用户管理'));
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('编辑'));
    await tester.tap(find.byTooltip('编辑'));
    await tester.pump();
    await tester.tap(find.text('保存'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('用户更新失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('alice'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('重置密码网络断开显示失败原文', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            if (path.contains('reset-password')) {
              expect(path, '/api/v2/Controller/1/reset-password');
              expect(method, 'POST');
              expect(body, {'new_password': 'newpass'});
              throw const SocketException('connection lost');
            }
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('用户管理'));
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('重置密码'));
    await tester.tap(find.byTooltip('重置密码'));
    await tester.pump();
    await tester.enterText(find.byType(TextField), 'newpass');
    await tester.tap(find.text('重置'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('密码重置失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('重置密码中退出再进入会丢掉错误', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('reset-password')) return pending.future;
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('用户管理'));
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('重置密码'));
    await tester.tap(find.byTooltip('重置密码'));
    await tester.pump();
    await tester.enterText(find.byType(TextField), 'newpass');
    await tester.tap(find.text('重置'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开管理后台'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.pump();
    expect(find.textContaining('密码重置失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('alice'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('切账号后旧账号的密码重置成功提示不会出现', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path.contains('reset-password')) return pending.future;
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('用户管理'));
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.byTooltip('重置密码'));
    await tester.tap(find.byTooltip('重置密码'));
    await tester.pump();
    await tester.enterText(find.byType(TextField), 'newpass');
    await tester.tap(find.text('重置'));
    await tester.pump();

    auth.switchAccount('bob');
    await tester.pump();
    await tester.pump();

    pending.complete(const <String, Object?>{});
    await tester.pumpAndSettle();

    expect(find.text('密码已重置'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('切账号后旧账号的系统配置弹层不会弹出', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, _, __) async {
            if (path == '/api/v2/admin/config') return pending.future;
            throw StateError('unexpected $path');
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('系统配置'));
    await tester.pump();

    auth.switchAccount('bob');
    await tester.pump();
    await tester.pump();

    pending.complete(const <String, Object?>{'token_ttl': 3600});
    await tester.pumpAndSettle();

    expect(find.text('系统配置'), findsOneWidget);
    expect(find.byType(AlertDialog), findsNothing);
    expect(find.textContaining('token_ttl'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('系统配置网络断开显示失败原文', (tester) async {
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, _, __) async {
            if (path.contains('/admin/config')) {
              throw const SocketException('connection lost');
            }
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('系统配置'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('配置读取失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('系统统计进行中无法再次触发并发请求', (tester) async {
    var statsCalls = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, _, __) async {
            if (path.contains('/admin/stats')) {
              statsCalls += 1;
              return pending.future;
            }
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('系统统计'));
    await tester.pump();
    expect(statsCalls, 1);
    await tester.tap(find.text('系统统计'));
    await tester.pump();
    expect(statsCalls, 1);
    pending.complete({'ok': true});
    await tester.pump();
    await tester.pump();
    expect(find.byType(AlertDialog), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('系统统计网络断开显示失败原文', (tester) async {
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, _, __) async {
            if (path.contains('/admin/stats')) {
              throw const SocketException('connection lost');
            }
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('系统统计'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('系统统计读取失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('系统统计失败后再次成功会清除旧错误', (tester) async {
    var statsCalls = 0;
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, _, __) async {
            if (path.contains('/admin/stats')) {
              statsCalls += 1;
              if (statsCalls == 1) {
                throw const SocketException('connection lost');
              }
              return {'ok': true};
            }
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('系统统计'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('系统统计读取失败'), findsOneWidget);
    await tester.tap(find.text('系统统计'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('系统统计读取失败'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('系统配置读取中退出再进入会丢掉错误', (tester) async {
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, _, __) async {
            if (path.contains('/admin/config')) return pending.future;
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('系统配置'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开管理后台'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.pump();
    expect(find.textContaining('配置读取失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('沙箱配置读取中退出再进入会丢掉错误', (tester) async {
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, _, __) async {
            if (path.contains('/admin/sandbox-config')) return pending.future;
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('沙箱配置'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开管理后台'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.pump();
    expect(find.textContaining('沙箱配置读取失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('系统统计读取中退出再进入会丢掉错误', (tester) async {
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, _, __) async {
            if (path.contains('/admin/stats')) return pending.future;
            return usersPayload;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('系统统计'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开管理后台'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.pump();
    expect(find.textContaining('系统统计读取失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('沙箱配置读取当前值后保存写入', (tester) async {
    final writes = <Map<String, Object?>>[];
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            if (path == '/api/v2/admin/sandbox-config') {
              if (method == 'PUT') {
                writes.add(
                  body is Map
                      ? Map<String, Object?>.from(body)
                      : const <String, Object?>{},
                );
                return {'success': true};
              }
              return {
                'enable_code_sandbox': true,
                'sandbox_languages': ['python', 'javascript'],
              };
            }
            throw StateError('unexpected $path');
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('沙箱配置'));
    await tester.pump();
    await tester.pump();
    expect(find.byType(AlertDialog), findsOneWidget);
    expect(
      tester
          .widget<SwitchListTile>(find.byKey(const Key('sandboxEnabledSwitch')))
          .value,
      isTrue,
    );
    expect(
      tester
          .widget<TextField>(find.byKey(const Key('sandboxLanguagesField')))
          .controller
          ?.text,
      'python,javascript',
    );

    await tester.tap(find.byKey(const Key('sandboxEnabledSwitch')));
    await tester.enterText(
      find.byKey(const Key('sandboxLanguagesField')),
      'python,go',
    );
    await tester.tap(find.text('保存'));
    await tester.pump();
    await tester.pump();

    expect(writes, [
      {'enable_code_sandbox': false, 'sandbox_languages': 'python,go'},
    ]);
    expect(find.textContaining('沙箱配置已更新'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('沙箱配置写入失败显示失败原文', (tester) async {
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path == '/api/v2/admin/sandbox-config') {
              if (method == 'PUT') {
                throw const SocketException('connection lost');
              }
              return {
                'enable_code_sandbox': false,
                'sandbox_languages': <String>[],
              };
            }
            throw StateError('unexpected $path');
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('沙箱配置'));
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('保存'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('沙箱配置更新失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('沙箱配置读取失败不打开弹层', (tester) async {
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi(
            (_, __, ___) async =>
                throw const SocketException('connection lost'),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('沙箱配置'));
    await tester.pump();
    await tester.pump();
    expect(find.byType(AlertDialog), findsNothing);
    expect(find.textContaining('沙箱配置读取失败'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('取消沙箱配置不发出写请求', (tester) async {
    var writes = 0;
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (method == 'PUT') writes++;
            return {
              'enable_code_sandbox': false,
              'sandbox_languages': <String>[],
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('沙箱配置'));
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('取消'));
    await tester.pump();
    expect(writes, 0);
    expect(tester.takeException(), isNull);
  });

  testWidgets('日志配置选择级别后写入全局级别', (tester) async {
    final writes = <String>[];
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (path == '/api/v2/Controller/admin/log-config') {
              expect(method, 'GET');
              return {'global_level': 'WARNING'};
            }
            if (path.startsWith(
              '/api/v2/Controller/admin/log-config/global-level',
            )) {
              expect(method, 'PUT');
              writes.add(path);
              return {'status': 'success'};
            }
            throw StateError('unexpected $path');
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('日志配置'));
    await tester.pump();
    await tester.pump();
    expect(
      tester
          .widget<DropdownButton<String>>(
            find.byKey(const Key('logLevelDropdown')),
          )
          .value,
      'WARNING',
    );

    await tester.tap(find.byKey(const Key('logLevelDropdown')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ERROR').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('保存'));
    await tester.pump();
    await tester.pump();

    expect(writes, [
      '/api/v2/Controller/admin/log-config/global-level?level=ERROR',
    ]);
    expect(find.textContaining('全局日志级别已更新为 ERROR'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('限流配置保存开关与三档规则', (tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final writes = <Map<String, Object?>>[];
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, body) async {
            if (path == '/api/v2/Controller/admin/rate-limit') {
              expect(method, 'GET');
              return {
                'enabled': true,
                'total_keys': 3,
                'config': {
                  'enabled': true,
                  'global': {'limit': 100, 'window': 60},
                  'by_ip': {'limit': 20, 'window': 60},
                  'by_user': {'limit': 10, 'window': 60},
                },
              };
            }
            if (method == 'PUT') {
              writes.add({
                'path': path,
                ...body is Map
                    ? Map<String, Object?>.from(body)
                    : const <String, Object?>{},
              });
              return {'status': 'success'};
            }
            throw StateError('unexpected $path');
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('限流配置'));
    await tester.pump();
    await tester.pump();
    expect(
      tester
          .widget<TextField>(find.byKey(const Key('rateLimitGlobalLimit')))
          .controller
          ?.text,
      '100',
    );
    expect(
      tester
          .widget<TextField>(find.byKey(const Key('rateLimitIpLimit')))
          .controller
          ?.text,
      '20',
    );

    await tester.enterText(find.byKey(const Key('rateLimitIpLimit')), '25');
    await tester.tap(find.byKey(const Key('rateLimitEnabledSwitch')));
    await tester.tap(find.text('保存'));
    await tester.pump();
    await tester.pump();

    expect(writes.length, 4);
    expect(writes.first['path'], contains('rate-limit/enabled?enabled=false'));
    expect(writes[1], {
      'path': '/api/v2/Controller/admin/rate-limit/global',
      'limit': 100,
      'window': 60,
    });
    expect(writes[2], {
      'path': '/api/v2/Controller/admin/rate-limit/ip',
      'limit': 25,
      'window': 60,
    });
    expect(writes[3], {
      'path': '/api/v2/Controller/admin/rate-limit/user',
      'limit': 10,
      'window': 60,
    });
    expect(tester.takeException(), isNull);
  });

  testWidgets('限流配置非正整数拒绝写入', (tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var writes = 0;
    final container = ProviderContainer(
      overrides: [
        authenticatedClientProvider.overrideWithValue(
          DeliveryApi((path, method, _) async {
            if (method == 'PUT') writes++;
            return {
              'enabled': true,
              'config': {
                'enabled': true,
                'global': {'limit': 100, 'window': 60},
                'by_ip': {'limit': 20, 'window': 60},
                'by_user': {'limit': 10, 'window': 60},
              },
            };
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: AdminPage()),
      ),
    );
    await tester.tap(find.text('限流配置'));
    await tester.pump();
    await tester.pump();
    await tester.enterText(find.byKey(const Key('rateLimitUserWindow')), '0');
    await tester.tap(find.text('保存'));
    await tester.pump();
    await tester.pump();
    expect(writes, 0);
    expect(find.textContaining('必须为正整数'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
