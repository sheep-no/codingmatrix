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
import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/application/provider_key_controller.dart';
import 'package:codingmatrix_desktop/domain/models/image_generation.dart';
import 'package:codingmatrix_desktop/domain/models/provider_key.dart';
import 'package:codingmatrix_desktop/infrastructure/image/image_generation_client.dart';
import 'package:codingmatrix_desktop/infrastructure/provider/provider_key_client.dart';
import 'package:codingmatrix_desktop/presentation/image_generation_page.dart';
import 'package:file_picker/file_picker.dart';
import 'agent_delivery_test.dart' show DeliveryApi;
import 'auth_session_test.dart' show Fixture;
import 'module_lifecycle_test.dart' show ModuleAuth;

const key = ProviderKeySummary(
  token: 'test-ref',
  provider: 'siliconflow',
  status: 'valid',
  enabled: true,
  expiresAt: null,
);
const openAiKey = ProviderKeySummary(
  token: 'test-openai-ref',
  provider: 'openai',
  status: 'valid',
  enabled: true,
  expiresAt: null,
);
const disabledKey = ProviderKeySummary(
  token: 'test-ref',
  provider: 'siliconflow',
  status: 'valid',
  enabled: false,
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

class TestImagePicker extends FilePicker {
  TestImagePicker(this.path);
  final String path;
  Object? error;
  Completer<FilePickerResult?>? pending;
  int picks = 0;
  @override
  Future<FilePickerResult?> pickFiles({
    String? dialogTitle,
    String? initialDirectory,
    FileType type = FileType.any,
    List<String>? allowedExtensions,
    Function(FilePickerStatus)? onFileLoading,
    bool allowCompression = true,
    int compressionQuality = 30,
    bool allowMultiple = false,
    bool withData = false,
    bool withReadStream = false,
    bool lockParentWindow = false,
    bool readSequential = false,
  }) async {
    if (error != null) throw error!;
    picks++;
    if (pending != null) return pending!.future;
    return FilePickerResult([
      PlatformFile(name: 'ref.png', path: path, size: 10),
    ]);
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
  test('快捷生成把 prompt 和 style 放在查询参数而不是请求体', () async {
    final requests = <Uri>[];
    final bodies = <Object?>[];
    final client = ImageGenerationClient(
      DeliveryApi((path, method, body) async {
        expect(method, 'POST');
        requests.add(Uri.parse(path));
        bodies.add(body);
        return {
          'success': true,
          'paths': ['generated_images/kolors_123.png'],
        };
      }),
    );
    for (final mode in ['avatar', 'landscape', 'icon']) {
      final result = await client.shortcut(mode, '红色 头像', 'anime');
      expect(result.sources.single, 'generated_images/kolors_123.png');
    }
    expect(requests.map((uri) => uri.path), [
      '/api/v1/kolors/avatar',
      '/api/v1/kolors/landscape',
      '/api/v1/kolors/icon',
    ]);
    for (final uri in requests) {
      expect(uri.queryParameters, {'prompt': '红色 头像', 'style': 'anime'});
    }
    expect(bodies, [null, null, null]);
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

  test('生成请求网络断开后退出忙碌并显示错误', () async {
    final controller = ImageGenerationController(
      ImageGenerationClient(
        DeliveryApi(
          (_, __, ___) async => throw const SocketException('connection lost'),
        ),
      ),
    );
    await controller.generate(const ImageGenerationInput(prompt: '山'), key);
    expect(controller.state.error, '生成请求失败或结果未知，请确认后手动提交');
    expect(controller.state.busy, false);
    expect(controller.state.images, isEmpty);
    controller.dispose();
  });

  test('图生图网络断开显示笼统错误', () async {
    final controller = ImageGenerationController(
      ImageGenerationClient(
        DeliveryApi((path, method, body) async {
          expect(path, '/api/v1/kolors/image-to-image');
          expect(method, 'POST');
          expect(body, {
            'image_path': '/tmp/ref.png',
            'prompt': '山',
            'api_key_token': 'test-ref',
          });
          throw const SocketException('connection lost');
        }),
      ),
    );
    await controller.imageToImage('/tmp/ref.png', '山', key);
    expect(controller.state.error, '图生图失败');
    expect(controller.state.busy, false);
    expect(controller.state.images, isEmpty);
    controller.dispose();
  });

  test('局部重绘网络断开显示笼统错误', () async {
    final controller = ImageGenerationController(
      ImageGenerationClient(
        DeliveryApi((path, method, body) async {
          expect(path, '/api/v1/kolors/inpaint');
          expect(method, 'POST');
          expect(body, {
            'image_path': '/tmp/ref.png',
            'mask_path': '/tmp/mask.png',
            'prompt': '山',
            'api_key_token': 'test-ref',
          });
          throw const SocketException('connection lost');
        }),
      ),
    );
    await controller.inpaint('/tmp/ref.png', '/tmp/mask.png', '山', key);
    expect(controller.state.error, '局部重绘失败');
    expect(controller.state.busy, false);
    expect(controller.state.images, isEmpty);
    controller.dispose();
  });

  test('图生图拒绝非 SiliconFlow 授权并提示', () async {
    var requests = 0;
    final controller = ImageGenerationController(
      ImageGenerationClient(
        DeliveryApi((_, __, ___) async {
          requests++;
          return null;
        }),
      ),
    );
    await controller.imageToImage('/tmp/ref.png', '山', openAiKey);
    expect(requests, 0);
    expect(controller.state.error, '请选择可用的 SiliconFlow 授权');
    expect(controller.state.images, isEmpty);
    controller.dispose();
  });

  test('局部重绘拒绝非 SiliconFlow 授权并提示', () async {
    var requests = 0;
    final controller = ImageGenerationController(
      ImageGenerationClient(
        DeliveryApi((_, __, ___) async {
          requests++;
          return null;
        }),
      ),
    );
    await controller.inpaint('/tmp/ref.png', '/tmp/mask.png', '山', openAiKey);
    expect(requests, 0);
    expect(controller.state.error, '请选择可用的 SiliconFlow 授权');
    controller.dispose();
  });

  test('快捷生成遇到不可用授权会提示而不是静默无反馈', () async {
    var requests = 0;
    final controller = ImageGenerationController(
      ImageGenerationClient(
        DeliveryApi((_, __, ___) async {
          requests++;
          return null;
        }),
      ),
    );
    await controller.shortcut('avatar', '山', 'realistic', disabledKey);
    expect(requests, 0);
    expect(controller.state.error, '请选择可用的 SiliconFlow 授权');
    controller.dispose();
  });

  test('图生图中途释放会丢掉晚到的错误', () async {
    final pending = Completer<Object?>();
    final controller = ImageGenerationController(
      ImageGenerationClient(DeliveryApi((_, __, ___) => pending.future)),
    );
    final future = controller.imageToImage('/tmp/ref.png', '山', key);
    expect(controller.state.busy, true);
    controller.dispose();
    pending.completeError(const SocketException('connection lost'));
    await future;
    expect(controller.mounted, false);
  });

  testWidgets('生成中退出再进入不会保留图片', (tester) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final pending = Completer<Object?>();
    final client = ImageGenerationClient(
      DeliveryApi((_, __, ___) => pending.future),
    );
    final container = ProviderContainer(
      overrides: [
        imageGenerationControllerProvider.overrideWith(
          (_) => ImageGenerationController(client),
        ),
        providerKeyControllerProvider.overrideWith((_) => ImageKeys()),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.enterText(find.byKey(const Key('imagePrompt')), '山');
    await tester.ensureVisible(find.byKey(const Key('imageGenerate')));
    await tester.tap(find.byKey(const Key('imageGenerate')));
    await tester.pump();
    expect(find.text('正在生成或读取图片，请等待'), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开图片'))),
      ),
    );
    await tester.pump();

    pending.complete({
      'success': true,
      'images': [pixel],
    });
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.pump();
    expect(find.text('图片 1'), findsNothing);
    expect(find.text('离开图片'), findsNothing);
  });

  testWidgets('生成中网络断开显示笼统错误', (tester) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final client = ImageGenerationClient(
      DeliveryApi(
        (_, __, ___) async => throw const SocketException('connection lost'),
      ),
    );
    final container = ProviderContainer(
      overrides: [
        imageGenerationControllerProvider.overrideWith(
          (_) => ImageGenerationController(client),
        ),
        providerKeyControllerProvider.overrideWith((_) => ImageKeys()),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.enterText(find.byKey(const Key('imagePrompt')), '山');
    await tester.ensureVisible(find.byKey(const Key('imageGenerate')));
    await tester.tap(find.byKey(const Key('imageGenerate')));
    await tester.pump();
    await tester.pump();
    expect(find.text('生成请求失败或结果未知，请确认后手动提交'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('正在生成或读取图片，请等待'), findsNothing);
    expect(find.text('图片 1'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('生成中退出再进入会丢掉错误', (tester) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final pending = Completer<Object?>();
    final client = ImageGenerationClient(
      DeliveryApi((_, __, ___) => pending.future),
    );
    final container = ProviderContainer(
      overrides: [
        imageGenerationControllerProvider.overrideWith(
          (_) => ImageGenerationController(client),
        ),
        providerKeyControllerProvider.overrideWith((_) => ImageKeys()),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.enterText(find.byKey(const Key('imagePrompt')), '山');
    await tester.ensureVisible(find.byKey(const Key('imageGenerate')));
    await tester.tap(find.byKey(const Key('imageGenerate')));
    await tester.pump();
    expect(find.text('正在生成或读取图片，请等待'), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开图片'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.pump();
    expect(find.text('生成请求失败或结果未知，请确认后手动提交'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('图片 1'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('快捷生成网络断开显示笼统错误', (tester) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final client = ImageGenerationClient(
      DeliveryApi(
        (_, __, ___) async => throw const SocketException('connection lost'),
      ),
    );
    final container = ProviderContainer(
      overrides: [
        imageGenerationControllerProvider.overrideWith(
          (_) => ImageGenerationController(client),
        ),
        providerKeyControllerProvider.overrideWith((_) => ImageKeys()),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.tap(find.text('生成头像'));
    await tester.pump();
    await tester.pump();
    expect(find.text('快捷图片生成失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('正在生成或读取图片，请等待'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('快捷生成中退出再进入会丢掉错误', (tester) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final pending = Completer<Object?>();
    final client = ImageGenerationClient(
      DeliveryApi((_, __, ___) => pending.future),
    );
    final container = ProviderContainer(
      overrides: [
        imageGenerationControllerProvider.overrideWith(
          (_) => ImageGenerationController(client),
        ),
        providerKeyControllerProvider.overrideWith((_) => ImageKeys()),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.tap(find.text('生成头像'));
    await tester.pump();
    expect(find.text('正在生成或读取图片，请等待'), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开图片'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.pump();
    expect(find.text('快捷图片生成失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('图片 1'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('选择参考图进行中无法再次打开选择器', (tester) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final pending = Completer<FilePickerResult?>();
    final picker = TestImagePicker('/tmp/ref.png')..pending = pending;
    FilePicker.platform = picker;
    final container = ProviderContainer(
      overrides: [
        imageGenerationControllerProvider.overrideWith(
          (_) => ImageGenerationController(
            ImageGenerationClient(DeliveryApi((_, __, ___) async => null)),
          ),
        ),
        providerKeyControllerProvider.overrideWith((_) => ImageKeys()),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.ensureVisible(find.text('选择参考图'));
    await tester.tap(find.text('选择参考图'));
    await tester.pump();
    expect(picker.picks, 1);
    await tester.tap(find.text('选择参考图'), warnIfMissed: false);
    await tester.pump();
    expect(picker.picks, 1);
    pending.complete(
      FilePickerResult([
        PlatformFile(name: 'ref.png', path: '/tmp/ref.png', size: 10),
      ]),
    );
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('图生图中退出再进入会丢掉错误', (tester) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final pending = Completer<Object?>();
    final client = ImageGenerationClient(
      DeliveryApi((path, _, __) async {
        if (path == '/api/v1/kolors/image-to-image') return pending.future;
        return {
          'success': true,
          'images': [pixel],
        };
      }),
    );
    FilePicker.platform = TestImagePicker('/tmp/ref.png');
    final container = ProviderContainer(
      overrides: [
        imageGenerationControllerProvider.overrideWith(
          (_) => ImageGenerationController(client),
        ),
        providerKeyControllerProvider.overrideWith((_) => ImageKeys()),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.ensureVisible(find.text('选择参考图'));
    await tester.tap(find.text('选择参考图'));
    await tester.pump();
    await tester.enterText(find.byKey(const Key('imagePrompt')), '山');
    await tester.ensureVisible(find.text('执行图生图'));
    await tester.tap(find.text('执行图生图'));
    await tester.pump();
    expect(find.text('正在生成或读取图片，请等待'), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开图片'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.pump();
    expect(find.text('图生图失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('图片 1'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('局部重绘中退出再进入会丢掉错误', (tester) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final pending = Completer<Object?>();
    final client = ImageGenerationClient(
      DeliveryApi((path, _, __) async {
        if (path == '/api/v1/kolors/inpaint') return pending.future;
        return {
          'success': true,
          'images': [pixel],
        };
      }),
    );
    FilePicker.platform = TestImagePicker('/tmp/ref.png');
    final container = ProviderContainer(
      overrides: [
        imageGenerationControllerProvider.overrideWith(
          (_) => ImageGenerationController(client),
        ),
        providerKeyControllerProvider.overrideWith((_) => ImageKeys()),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.ensureVisible(find.text('选择参考图'));
    await tester.tap(find.text('选择参考图'));
    await tester.pump();
    await tester.ensureVisible(find.text('选择蒙版'));
    await tester.tap(find.text('选择蒙版'));
    await tester.pump();
    await tester.enterText(find.byKey(const Key('imagePrompt')), '山');
    await tester.ensureVisible(find.text('执行局部重绘'));
    await tester.tap(find.text('执行局部重绘'));
    await tester.pump();
    expect(find.text('正在生成或读取图片，请等待'), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开图片'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.pump();
    expect(find.text('局部重绘失败'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.text('图片 1'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('保存中退出再进入会丢掉已保存路径和错误', (tester) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final pending = Completer<Directory>();
    final client = ImageGenerationClient(
      DeliveryApi(
        (_, __, ___) async => {
          'success': true,
          'images': [pixel],
        },
      ),
      directory: () => pending.future,
    );
    final container = ProviderContainer(
      overrides: [
        imageGenerationControllerProvider.overrideWith(
          (_) => ImageGenerationController(client),
        ),
        providerKeyControllerProvider.overrideWith((_) => ImageKeys()),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.enterText(find.byKey(const Key('imagePrompt')), '山');
    await tester.ensureVisible(find.byKey(const Key('imageGenerate')));
    await tester.tap(find.byKey(const Key('imageGenerate')));
    await tester.pumpAndSettle();
    expect(find.text('图片 1'), findsOneWidget);
    await tester.ensureVisible(find.text('保存到应用文档目录'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('保存到应用文档目录'));
    await tester.pump();
    expect(find.text('正在保存'), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开图片'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.pump();
    expect(find.text('保存失败，图片预览已保留'), findsNothing);
    expect(find.textContaining('connection lost'), findsNothing);
    expect(find.textContaining('已保存：'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('选择参考图失败显示失败原文', (tester) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    FilePicker.platform = TestImagePicker('/tmp/ref.png')
      ..error = const SocketException('connection lost');
    final client = ImageGenerationClient(
      DeliveryApi(
        (_, __, ___) async => {
          'success': true,
          'images': [pixel],
        },
      ),
    );
    final container = ProviderContainer(
      overrides: [
        imageGenerationControllerProvider.overrideWith(
          (_) => ImageGenerationController(client),
        ),
        providerKeyControllerProvider.overrideWith((_) => ImageKeys()),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.ensureVisible(find.text('选择参考图'));
    await tester.tap(find.text('选择参考图'));
    await tester.pump();
    expect(find.textContaining('选择图片失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('已选择参考图'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('切换账号后旧账号选择的参考图不会写入新账号', (tester) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    final picker = TestImagePicker('/tmp/ref.png')
      ..pending = Completer<FilePickerResult?>();
    FilePicker.platform = picker;
    final client = ImageGenerationClient(
      DeliveryApi(
        (_, __, ___) async => {
          'success': true,
          'images': [pixel],
        },
      ),
    );
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        imageGenerationControllerProvider.overrideWith(
          (_) => ImageGenerationController(client),
        ),
        providerKeyControllerProvider.overrideWith((_) => ImageKeys()),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.ensureVisible(find.text('选择参考图'));
    await tester.tap(find.text('选择参考图'));
    await tester.pump();

    auth.switchAccount('bob');
    await tester.pump();
    await tester.pump();

    picker.pending!.complete(
      FilePickerResult([
        PlatformFile(name: 'ref.png', path: '/tmp/ref.png', size: 10),
      ]),
    );
    await tester.pumpAndSettle();

    expect(find.text('已选择参考图'), findsNothing);
    expect(find.text('执行图生图'), findsNothing);
    expect(find.text('选择参考图'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('切换账号清空参考图草稿', (tester) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final auth = ModuleAuth(Fixture())..switchAccount('alice');
    FilePicker.platform = TestImagePicker('/tmp/ref.png');
    final client = ImageGenerationClient(
      DeliveryApi(
        (_, __, ___) async => {
          'success': true,
          'images': [pixel],
        },
      ),
    );
    final container = ProviderContainer(
      overrides: [
        authControllerProvider.overrideWith((_) => auth),
        imageGenerationControllerProvider.overrideWith(
          (_) => ImageGenerationController(client),
        ),
        providerKeyControllerProvider.overrideWith((_) => ImageKeys()),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ImageGenerationPage()),
      ),
    );
    await tester.ensureVisible(find.text('选择参考图'));
    await tester.tap(find.text('选择参考图'));
    await tester.pump();
    expect(find.text('已选择参考图'), findsOneWidget);
    expect(find.text('执行图生图'), findsOneWidget);

    auth.switchAccount('bob');
    await tester.pumpAndSettle();

    expect(find.text('已选择参考图'), findsNothing);
    expect(find.text('执行图生图'), findsNothing);
    expect(find.text('选择参考图'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
