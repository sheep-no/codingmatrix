import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/credential_store.dart';
import 'package:codingmatrix_desktop/presentation/login_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

ProviderContainer loginContainer(http.Client httpClient) {
  final store = CredentialStore();
  return ProviderContainer(
    overrides: [
      credentialStoreProvider.overrideWithValue(store),
      httpClientProvider.overrideWithValue(httpClient),
      authControllerProvider.overrideWith((ref) {
        return AuthController(
          ref.watch(cloudAuthClientProvider),
          ref.watch(credentialStoreProvider),
        );
      }),
    ],
  );
}

Future<void> pumpLogin(WidgetTester tester, ProviderContainer container) async {
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: LoginPage()),
    ),
  );
  await tester.pump();
}

Future<void> fillLogin(WidgetTester tester) async {
  await tester.enterText(
    find.byKey(const Key('emailField')),
    'alice@example.com',
  );
  await tester.enterText(find.byKey(const Key('passwordField')), 'secret');
}

void main() {
  testWidgets('空邮箱不会发起登录请求', (tester) async {
    var calls = 0;
    final container = loginContainer(
      MockClient((_) async {
        calls++;
        throw const SocketException('connection lost');
      }),
    );
    addTearDown(container.dispose);

    await pumpLogin(tester, container);
    await tester.tap(find.byKey(const Key('loginButton')));
    await tester.pump();
    expect(find.text('请输入有效邮箱'), findsOneWidget);
    expect(calls, 0);
  });

  testWidgets('网络断开显示认证连接失败', (tester) async {
    final container = loginContainer(
      MockClient((_) async => throw const SocketException('connection lost')),
    );
    addTearDown(container.dispose);

    await pumpLogin(tester, container);
    await fillLogin(tester);
    await tester.tap(find.byKey(const Key('loginButton')));
    await tester.pump();
    await tester.pump();
    expect(find.byKey(const Key('loginError')), findsOneWidget);
    expect(find.text('认证连接失败，请检查网络后重试'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
  });

  testWidgets('登录中显示进度并禁用按钮', (tester) async {
    final pending = Completer<http.Response>();
    final container = loginContainer(MockClient((_) => pending.future));
    addTearDown(container.dispose);

    await pumpLogin(tester, container);
    await fillLogin(tester);
    await tester.tap(find.byKey(const Key('loginButton')));
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('loginButton')))
          .onPressed,
      isNull,
    );
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
  });

  testWidgets('登录进行中回车不会重复发起请求', (tester) async {
    var calls = 0;
    final pending = Completer<http.Response>();
    final container = loginContainer(
      MockClient((_) {
        calls++;
        return pending.future;
      }),
    );
    addTearDown(container.dispose);

    await pumpLogin(tester, container);
    await fillLogin(tester);
    await tester.tap(find.byKey(const Key('loginButton')));
    await tester.pump();
    expect(calls, 1);

    tester
        .widget<TextField>(
          find.descendant(
            of: find.byKey(const Key('passwordField')),
            matching: find.byType(TextField),
          ),
        )
        .onSubmitted
        ?.call('secret');
    await tester.pump();
    expect(calls, 1);

    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
  });

  testWidgets('登录中退出再进入会保留错误并清空表单', (tester) async {
    final pending = Completer<http.Response>();
    final container = loginContainer(MockClient((_) => pending.future));
    addTearDown(container.dispose);

    await pumpLogin(tester, container);
    await fillLogin(tester);
    await tester.tap(find.byKey(const Key('loginButton')));
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开登录'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await pumpLogin(tester, container);
    expect(find.text('认证连接失败，请检查网络后重试'), findsOneWidget);
    expect(
      tester
          .widget<TextFormField>(find.byKey(const Key('emailField')))
          .controller
          ?.text,
      isEmpty,
    );
    expect(
      tester
          .widget<TextFormField>(find.byKey(const Key('passwordField')))
          .controller
          ?.text,
      isEmpty,
    );
  });
}
