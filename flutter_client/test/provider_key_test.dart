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
}
