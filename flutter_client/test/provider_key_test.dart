import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';
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
}
