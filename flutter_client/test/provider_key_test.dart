import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';
import 'dart:async';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:codingmatrix_desktop/presentation/provider_settings_page.dart';
import 'package:http/http.dart' as http;
import 'package:pointycastle/export.dart';
import 'package:pointycastle/asn1.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/authenticated_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/cloud_auth_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/credential_store.dart';
import 'package:codingmatrix_desktop/infrastructure/provider/provider_key_client.dart';
import 'package:codingmatrix_desktop/application/provider_key_controller.dart';
import 'package:codingmatrix_desktop/application/auth_controller.dart';

import 'auth_session_test.dart' show Fixture;
import 'module_lifecycle_test.dart' show ModuleAuth;

class RecordingApi extends AuthenticatedClient {
  RecordingApi(this.handler)
    : super(
        CloudAuthClient(
          baseUrl: 'https://example.com',
          httpClient: http.Client(),
          credentialStore: CredentialStore(),
        ),
        http.Client(),
      );
  final Future<Object?> Function(String, String, Object?) handler;
  @override
  Future<Object?> requestJson(
    String path, {
    String method = 'GET',
    Object? body,
    Duration? timeout,
  }) => handler(path, method, body);
}

void main() {
  testWidgets('compact settings masks token and asks before deletion', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(360, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var deletes = 0;
    final client = ProviderKeyClient(
      RecordingApi((path, method, body) async {
        if (method == 'DELETE') {
          deletes++;
          return {};
        }
        return [
          {
            'token': 'sensitive-token-reference',
            'provider': 'openai',
            'status': 'verified',
            'enabled': true,
            'expires_at': DateTime.now()
                .add(const Duration(hours: 1))
                .toIso8601String(),
          },
        ];
      }),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          providerKeyControllerProvider.overrideWith(
            (ref) => ProviderKeyController(client),
          ),
        ],
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('sensitive-token'), findsNothing);
    await tester.tap(find.text('用于生成'));
    await tester.pump();
    expect(find.text('当前生成授权'), findsOneWidget);
    await tester.tap(find.byTooltip('删除授权'));
    await tester.pumpAndSettle();
    expect(deletes, 0);
    await tester.tap(find.text('取消'));
    await tester.pumpAndSettle();
    expect(deletes, 0);
    expect(tester.takeException(), isNull);
  });
  test(
    'SPKI key submission uses randomized OAEP SHA256 and token response',
    () async {
      final secure = Random.secure();
      final random = FortunaRandom()
        ..seed(
          KeyParameter(
            Uint8List.fromList(List.generate(32, (_) => secure.nextInt(256))),
          ),
        );
      final generator = RSAKeyGenerator()
        ..init(
          ParametersWithRandom(
            RSAKeyGeneratorParameters(BigInt.from(65537), 2048, 64),
            random,
          ),
        );
      final pair = generator.generateKeyPair();
      final public = pair.publicKey as RSAPublicKey;
      final rsa = ASN1Sequence(
        elements: [ASN1Integer(public.modulus), ASN1Integer(public.exponent)],
      );
      final spki = ASN1Sequence(
        elements: [
          ASN1Sequence(
            elements: [
              ASN1ObjectIdentifier.fromIdentifierString('1.2.840.113549.1.1.1'),
              ASN1Null(),
            ],
          ),
          ASN1BitString(stringValues: rsa.encode()),
        ],
      );
      final pem =
          '-----BEGIN PUBLIC KEY-----\n${base64Encode(spki.encode())}\n-----END PUBLIC KEY-----';
      final ciphertexts = <String>[];
      final client = ProviderKeyClient(
        RecordingApi((path, method, body) async {
          if (path.endsWith('/public-key')) return {'public_key': pem};
          expect(path, '/api/v1/agent/apikey');
          expect(method, 'POST');
          final payload = body as Map;
          expect(payload['provider'], 'siliconflow');
          expect(payload['ttl'], 86400);
          final encrypted = payload['encrypted_key'] as String;
          ciphertexts.add(encrypted);
          final decrypt = OAEPEncoding.withSHA256(RSAEngine())
            ..init(
              false,
              PrivateKeyParameter<RSAPrivateKey>(
                pair.privateKey as RSAPrivateKey,
              ),
            );
          expect(
            utf8.decode(decrypt.process(base64Decode(encrypted))),
            'test-provider-secret',
          );
          return {'success': true, 'token': 'opaque-reference'};
        }),
      );
      expect(
        await client.submit(
          key: 'test-provider-secret',
          provider: 'siliconflow',
        ),
        'opaque-reference',
      );
      await client.submit(key: 'test-provider-secret', provider: 'siliconflow');
      expect(ciphertexts[0], isNot(ciphertexts[1]));
    },
  );

  test('list selection, disable and delete follow backend contracts', () async {
    var enabled = true;
    var deleted = false;
    final client = ProviderKeyClient(
      RecordingApi((path, method, body) async {
        if (method == 'PUT') {
          expect(path, '/api/v1/agent/apikey/ref/enabled?enabled=false');
          enabled = false;
          return {};
        }
        if (method == 'DELETE') {
          expect(path, '/api/v1/agent/apikey/ref');
          deleted = true;
          return {};
        }
        expect(path, '/api/v1/agent/apikeys');
        return deleted
            ? []
            : [
                {
                  'token': 'ref',
                  'provider': 'openai',
                  'status': 'verified',
                  'enabled': enabled,
                  'expires_at': DateTime.now()
                      .add(const Duration(hours: 1))
                      .toIso8601String(),
                },
              ];
      }),
    );
    final controller = ProviderKeyController(client);
    await controller.load();
    controller.select(controller.state.items.single);
    expect(controller.state.selected?.token, 'ref');
    await controller.toggle(controller.state.items.single);
    expect(controller.state.selected, isNull);
    await controller.remove(controller.state.items.single);
    expect(controller.state.items, isEmpty);
    controller.dispose();
  });

  test('HTTP success with failed key test remains a failure', () async {
    final client = ProviderKeyClient(
      RecordingApi((path, method, body) async {
        expect(path, '/api/v1/agent/apikey/test');
        expect(body, {'token': 'ref'});
        return {'success': false, 'message': 'private provider detail'};
      }),
    );
    await expectLater(client.test('ref'), throwsStateError);
  });

  testWidgets('加载中网络断开显示配置加载失败', (tester) async {
    final container = ProviderContainer(
      overrides: [
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(
              RecordingApi(
                (_, __, ___) async =>
                    throw const SocketException('connection lost'),
              ),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('Provider 配置加载失败，请重试'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
  });

  testWidgets('加载后显示授权且不展示 token', (tester) async {
    final container = ProviderContainer(
      overrides: [
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(
              RecordingApi(
                (_, __, ___) async => [
                  {
                    'token': 'sensitive-token-reference',
                    'provider': 'openai',
                    'status': 'verified',
                    'enabled': true,
                    'expires_at': DateTime.now()
                        .add(const Duration(hours: 1))
                        .toIso8601String(),
                  },
                ],
              ),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('openai · 授权 1'), findsOneWidget);
    expect(find.textContaining('verified'), findsOneWidget);
    expect(find.textContaining('sensitive-token'), findsNothing);
  });

  testWidgets('切换账号清空已输入的 Key 并重新拉取列表', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    var calls = 0;
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(
              RecordingApi((_, __, ___) async {
                calls++;
                return [];
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(calls, 1);

    await tester.enterText(find.byType(TextField), 'sk-alice-secret');
    expect(find.text('sk-alice-secret'), findsOneWidget);

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    expect(find.text('sk-alice-secret'), findsNothing);
    expect(calls, 2);
    expect(tester.takeException(), isNull);
  });

  testWidgets('加载中退出再进入会重新拉取列表', (tester) async {
    var calls = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(
              RecordingApi((_, __, ___) async {
                calls++;
                if (calls == 1) return pending.future;
                return [
                  {
                    'token': 'sensitive-token-reference',
                    'provider': 'openai',
                    'status': 'verified',
                    'enabled': true,
                    'expires_at': DateTime.now()
                        .add(const Duration(hours: 1))
                        .toIso8601String(),
                  },
                ];
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    expect(find.text('Provider 设置'), findsOneWidget);
    expect(find.text('openai · 授权 1'), findsNothing);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 Provider'))),
      ),
    );
    await tester.pump();
    pending.complete([
      {
        'token': 'old-token',
        'provider': 'anthropic',
        'status': 'verified',
        'enabled': true,
        'expires_at': DateTime.now()
            .add(const Duration(hours: 1))
            .toIso8601String(),
      },
    ]);
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('openai · 授权 1'), findsOneWidget);
    expect(find.textContaining('anthropic'), findsNothing);
    expect(find.textContaining('sensitive-token'), findsNothing);
    expect(calls, 2);
  });

  testWidgets('空 Key 不会提交', (tester) async {
    var submits = 0;
    final container = ProviderContainer(
      overrides: [
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(
              RecordingApi((path, method, body) async {
                if (path.contains('/apikeys')) return [];
                submits += 1;
                return {'public_key': 'unused'};
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('添加 Provider Key'));
    await tester.pump();
    expect(submits, 0);
    expect(find.text('Provider Key 提交失败，请检查输入后重试'), findsNothing);
  });

  testWidgets('添加网络断开显示提交失败', (tester) async {
    final container = ProviderContainer(
      overrides: [
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(
              RecordingApi((path, method, body) async {
                if (path.contains('/apikeys')) return [];
                throw const SocketException('connection lost');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.enterText(find.byType(TextField), 'sk-test');
    await tester.tap(find.text('添加 Provider Key'));
    await tester.pump();
    await tester.pump();
    expect(find.text('Provider Key 提交失败，请检查输入后重试'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller?.text,
      'sk-test',
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('添加中退出再进入会清空输入并重新拉列表', (tester) async {
    var lists = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(
              RecordingApi((path, method, body) async {
                if (path.contains('/apikeys')) {
                  lists += 1;
                  if (lists == 1) return [];
                  return [
                    {
                      'token': 'sensitive-token-reference',
                      'provider': 'openai',
                      'status': 'verified',
                      'enabled': true,
                      'expires_at': DateTime.now()
                          .add(const Duration(hours: 1))
                          .toIso8601String(),
                    },
                  ];
                }
                return pending.future;
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.enterText(find.byType(TextField), 'sk-test');
    await tester.tap(find.text('添加 Provider Key'));
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 Provider'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('openai · 授权 1'), findsOneWidget);
    expect(find.text('Provider Key 提交失败，请检查输入后重试'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller?.text,
      isEmpty,
    );
  });

  Map<String, Object> listedKey() => {
    'token': 'sensitive-token-reference',
    'provider': 'openai',
    'status': 'verified',
    'enabled': true,
    'expires_at': DateTime.now()
        .add(const Duration(hours: 1))
        .toIso8601String(),
  };

  testWidgets('测试连接网络断开显示测试失败', (tester) async {
    final container = ProviderContainer(
      overrides: [
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(
              RecordingApi((path, method, body) async {
                if (path == '/api/v1/agent/apikeys') return [listedKey()];
                throw const SocketException('connection lost');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('测试连接'));
    await tester.pump();
    await tester.pump();
    expect(find.text('Provider Key 测试失败，请重试'), findsOneWidget);
    expect(find.text('连接测试通过'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.textContaining('sensitive-token'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('测试连接中退出再进入会丢掉错误并重新拉列表', (tester) async {
    var lists = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(
              RecordingApi((path, method, body) async {
                if (path == '/api/v1/agent/apikeys') {
                  lists += 1;
                  return [listedKey()];
                }
                if (path == '/api/v1/agent/apikey/test') return pending.future;
                throw StateError('unexpected $method $path');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('测试连接'));
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 Provider'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('Provider Key 测试失败，请重试'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('openai · 授权 1'), findsOneWidget);
    expect(lists, 2);
    expect(tester.takeException(), isNull);
  });

  testWidgets('切账号后旧账号的测试连接成功提示不会出现', (tester) async {
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(
              RecordingApi((path, method, body) async {
                if (path == '/api/v1/agent/apikeys') return [listedKey()];
                if (path == '/api/v1/agent/apikey/test') return pending.future;
                throw StateError('unexpected $method $path');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.text('测试连接'));
    await tester.pump();

    auth.switchAccount('bob');
    await tester.pump();
    await tester.pump();

    pending.complete({'success': true});
    await tester.pumpAndSettle();

    expect(find.text('连接测试通过'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('删除网络断开显示删除失败', (tester) async {
    final container = ProviderContainer(
      overrides: [
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(
              RecordingApi((path, method, body) async {
                if (path == '/api/v1/agent/apikeys') return [listedKey()];
                throw const SocketException('connection lost');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byTooltip('删除授权'));
    await tester.pump();
    await tester.tap(find.text('确认'));
    await tester.pump();
    await tester.pump();
    expect(find.text('删除 Provider Key 失败，请重试'), findsOneWidget);
    expect(find.text('openai · 授权 1'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('删除中退出再进入会重新拉列表', (tester) async {
    var lists = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(
              RecordingApi((path, method, body) async {
                if (path == '/api/v1/agent/apikeys') {
                  lists += 1;
                  return [listedKey()];
                }
                if (method == 'DELETE') return pending.future;
                throw StateError('unexpected $method $path');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byTooltip('删除授权'));
    await tester.pump();
    await tester.tap(find.text('确认'));
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 Provider'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('openai · 授权 1'), findsOneWidget);
    expect(find.text('删除 Provider Key 失败，请重试'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(lists, 2);
  });

  testWidgets('切换启用网络断开显示更新失败', (tester) async {
    final container = ProviderContainer(
      overrides: [
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(
              RecordingApi((path, method, body) async {
                if (path == '/api/v1/agent/apikeys') return [listedKey()];
                throw const SocketException('connection lost');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byType(Switch));
    await tester.pump();
    await tester.pump();
    expect(find.text('更新 Provider 状态失败，请重试'), findsOneWidget);
    expect(find.textContaining('已启用'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('忙碌中再次切换不会发请求', (tester) async {
    var puts = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(
              RecordingApi((path, method, body) async {
                if (path == '/api/v1/agent/apikeys') return [listedKey()];
                if (method == 'PUT') {
                  puts += 1;
                  return pending.future;
                }
                throw StateError('unexpected $method $path');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byType(Switch));
    await tester.pump();
    expect(puts, 1);
    await tester.tap(find.byType(Switch));
    await tester.pump();
    expect(puts, 1);
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
  });

  testWidgets('切换中退出再进入会重新拉列表', (tester) async {
    var lists = 0;
    final pending = Completer<Object?>();
    final container = ProviderContainer(
      overrides: [
        providerKeyControllerProvider.overrideWith(
          (_) => ProviderKeyController(
            ProviderKeyClient(
              RecordingApi((path, method, body) async {
                if (path == '/api/v1/agent/apikeys') {
                  lists += 1;
                  return [listedKey()];
                }
                if (method == 'PUT') return pending.future;
                throw StateError('unexpected $method $path');
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.tap(find.byType(Switch));
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开 Provider'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ProviderSettingsPage()),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('openai · 授权 1'), findsOneWidget);
    expect(find.text('更新 Provider 状态失败，请重试'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(lists, 2);
  });
}
