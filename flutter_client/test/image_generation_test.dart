import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/authenticated_client.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:codingmatrix_desktop/application/image_generation_controller.dart';
import 'package:codingmatrix_desktop/application/provider_key_controller.dart';
import 'package:codingmatrix_desktop/domain/models/image_generation.dart';
import 'package:codingmatrix_desktop/domain/models/provider_key.dart';
import 'package:codingmatrix_desktop/infrastructure/image/image_generation_client.dart';
import 'package:codingmatrix_desktop/infrastructure/provider/provider_key_client.dart';
import 'package:codingmatrix_desktop/presentation/image_generation_page.dart';
import 'agent_delivery_test.dart' show DeliveryApi;
import 'auth_session_test.dart' show Fixture;

const key = ProviderKeySummary(
  token: 'test-ref',
  provider: 'siliconflow',
  status: 'valid',
  enabled: true,
  expiresAt: null,
);
const pixel =
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII=';

class ImageKeys extends ProviderKeyController {
  ImageKeys()
    : super(ProviderKeyClient(DeliveryApi((_, __, ___) async => null))) {
    state = const ProviderKeyState(items: [key], selectedToken: 'test-ref');
  }
}

void main() {
  test(
    'cached resource uses authenticated route and saves exact bytes',
    () async {
      final fixture = Fixture();
      await fixture.login();
      final bytes = base64Decode(pixel.split(',').last);
      final transport = MockClient((request) async {
        expect(request.url.path, '/api/v1/kolors/resources/kolors_123.png');
        expect(request.headers['authorization'], startsWith('Bearer '));
        return http.Response.bytes(bytes, 200);
      });
      final folder = await Directory('/tmp/opencode').createTemp('image-save-');
      addTearDown(() => folder.delete(recursive: true));
      final client = ImageGenerationClient(
        AuthenticatedClient(fixture.auth, transport),
        directory: () async => folder,
      );
      final downloaded = await client.read(
        '/server/generated_images/kolors_123.png',
      );
      final path = await client.save(downloaded, () => true);
      expect(await File(path).readAsBytes(), bytes);
      expect(path, endsWith('.png'));
      await expectLater(client.save(bytes, () => false), throwsStateError);
      expect(await folder.list().length, 1);
    },
  );
  test('Kolors sends canonical parameters and handles cached paths', () async {
    final api = DeliveryApi((path, method, body) async {
      expect(path, '/api/v1/kolors/text-to-image');
      expect(method, 'POST');
      expect(body, {
        'prompt': '山',
        'negative_prompt': '',
        'width': 512,
        'height': 512,
        'num_inferences': 20,
        'guidance_scale': 7.5,
        'num_images': 1,
        'seed': 42,
        'api_key_token': 'test-ref',
      });
      return {
        'success': true,
        'images': [],
        'paths': ['generated_images/kolors_123.png'],
        'cached': true,
      };
    });
    final client = ImageGenerationClient(api);
    final result = await client.generate(
      const ImageGenerationInput(
        prompt: ' 山 ',
        width: 512,
        height: 512,
        steps: 20,
        seed: 42,
      ),
      'test-ref',
    );
    expect(result.cached, true);
    expect(result.sources.single, 'generated_images/kolors_123.png');
    expect(await client.read(pixel), base64Decode(pixel.split(',').last));
    await expectLater(
      client.read('https://other.example/image.png'),
      throwsStateError,
    );
  });
  test('business failure and empty success are rejected', () async {
    for (final result in [
      {'success': false},
      {'success': true, 'images': []},
    ]) {
      final client = ImageGenerationClient(
        DeliveryApi((_, __, ___) async => result),
      );
      await expectLater(
        client.generate(const ImageGenerationInput(prompt: 'x'), 'ref'),
        throwsStateError,
      );
    }
  });
  test(
    'one submission while waiting and disposal ignores late results',
    () async {
      final pending = Completer<Object?>();
      var calls = 0;
      final controller = ImageGenerationController(
        ImageGenerationClient(
          DeliveryApi((_, __, ___) {
            calls++;
            return pending.future;
          }),
        ),
      );
      final run = controller.generate(
        const ImageGenerationInput(prompt: 'x'),
        key,
      );
      await controller.generate(const ImageGenerationInput(prompt: 'x'), key);
      expect(calls, 1);
      expect(controller.state.busy, true);
      controller.dispose();
      pending.complete({
        'success': true,
        'images': [pixel],
      });
      await run;
    },
  );
  test(
    'invalid authorization sends no POST and failed image preserves result',
    () async {
      var calls = 0;
      final controller = ImageGenerationController(
        ImageGenerationClient(
          DeliveryApi((_, __, ___) async {
            calls++;
            return {
              'success': true,
              'images': ['unsupported'],
            };
          }),
        ),
      );
      await controller.generate(const ImageGenerationInput(prompt: 'x'), null);
      expect(calls, 0);
      expect(controller.state.error, isNotNull);
      await controller.generate(const ImageGenerationInput(prompt: 'x'), key);
      expect(controller.state.images.single.error, isNotNull);
      expect(controller.state.busy, false);
      await controller.reload(0);
      expect(calls, 1);
      controller.dispose();
    },
  );
  testWidgets('compact form validates and displays generation results', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final client = ImageGenerationClient(
      DeliveryApi(
        (_, __, ___) async => {
          'success': true,
          'images': [pixel],
        },
      ),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          imageGenerationControllerProvider.overrideWith(
            (_) => ImageGenerationController(client),
          ),
          providerKeyControllerProvider.overrideWith((_) => ImageKeys()),
        ],
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.ensureVisible(find.byKey(const Key('imageGenerate')));
    await tester.tap(find.byKey(const Key('imageGenerate')));
    await tester.pump();
    expect(find.text('请输入画面描述'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('imagePrompt')), '山');
    await tester.ensureVisible(find.byKey(const Key('imageGenerate')));
    await tester.tap(find.byKey(const Key('imageGenerate')));
    await tester.pumpAndSettle();
    expect(find.text('图片 1'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
