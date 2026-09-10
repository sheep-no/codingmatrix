// ignore_for_file: curly_braces_in_flow_control_structures
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../domain/models/image_generation.dart';
import '../domain/models/provider_key.dart';
import '../infrastructure/image/image_generation_client.dart';
import 'auth_controller.dart';

class ImageGenerationState {
  const ImageGenerationState({
    this.busy = false,
    this.cached = false,
    this.images = const [],
    this.error,
    this.saving,
  });
  final bool busy, cached;
  final List<GeneratedImage> images;
  final String? error;
  final int? saving;
}

class ImageGenerationController extends StateNotifier<ImageGenerationState> {
  ImageGenerationController(this.client) : super(const ImageGenerationState());
  final ImageGenerationClient client;
  int _operation = 0;
  bool _active(int op) => mounted && op == _operation;

  Future<void> generate(
    ImageGenerationInput input,
    ProviderKeySummary? key,
  ) async {
    if (!mounted || state.busy || state.saving != null) return;
    if (!input.valid ||
        key == null ||
        !key.isUsable ||
        key.provider != 'siliconflow') {
      state = const ImageGenerationState(error: '请填写有效参数并选择可用的 SiliconFlow 授权');
      return;
    }
    final op = ++_operation;
    state = const ImageGenerationState(busy: true);
    try {
      final result = await client.generate(input, key.token);
      if (!_active(op)) return;
      state = ImageGenerationState(
        busy: true,
        cached: result.cached,
        images: result.sources.map((s) => GeneratedImage(source: s)).toList(),
      );
      for (var i = 0; i < result.sources.length; i++) {
        await _read(i, op);
        if (!_active(op)) return;
      }
      state = ImageGenerationState(images: state.images, cached: result.cached);
    } catch (_) {
      if (_active(op)) {
        state = const ImageGenerationState(error: '生成请求失败或结果未知，请确认后手动提交');
      }
    }
  }

  Future<void> shortcut(
    String mode,
    String prompt,
    String style,
    ProviderKeySummary? key,
  ) async {
    if (!mounted ||
        state.busy ||
        key == null ||
        !key.isUsable ||
        key.provider != 'siliconflow')
      return;
    final op = ++_operation;
    state = const ImageGenerationState(busy: true);
    try {
      final result = await client.shortcut(mode, prompt, style);
      if (!_active(op)) return;
      state = ImageGenerationState(
        busy: true,
        images: result.sources.map((s) => GeneratedImage(source: s)).toList(),
      );
      for (var i = 0; i < result.sources.length; i++) await _read(i, op);
      if (_active(op)) state = ImageGenerationState(images: state.images);
    } catch (_) {
      if (_active(op)) state = const ImageGenerationState(error: '快捷图片生成失败');
    }
  }

  Future<void> _read(int index, int op) async {
    final image = state.images[index];
    GeneratedImage updated;
    try {
      updated = GeneratedImage(
        source: image.source,
        bytes: await client.read(image.source),
      );
    } catch (_) {
      updated = GeneratedImage(source: image.source, error: '图片读取失败，可重新加载');
    }
    if (!_active(op)) return;
    final images = [...state.images]..[index] = updated;
    state = ImageGenerationState(
      images: images,
      busy: state.busy,
      cached: state.cached,
    );
  }

  Future<void> imageToImage(
    String imagePath,
    String prompt,
    ProviderKeySummary? key,
  ) async {
    if (!mounted ||
        state.busy ||
        key == null ||
        !key.isUsable ||
        prompt.trim().isEmpty)
      return;
    final op = ++_operation;
    state = const ImageGenerationState(busy: true);
    try {
      final result = await client.imageToImage(
        imagePath: imagePath,
        prompt: prompt,
        token: key.token,
      );
      if (!_active(op)) return;
      state = ImageGenerationState(
        busy: true,
        cached: result.cached,
        images: result.sources.map((s) => GeneratedImage(source: s)).toList(),
      );
      for (var i = 0; i < result.sources.length; i++) await _read(i, op);
      if (_active(op))
        state = ImageGenerationState(
          images: state.images,
          cached: result.cached,
        );
    } catch (_) {
      if (_active(op)) state = const ImageGenerationState(error: '图生图失败');
    }
  }

  Future<void> inpaint(
    String imagePath,
    String maskPath,
    String prompt,
    ProviderKeySummary? key,
  ) async {
    if (!mounted ||
        state.busy ||
        key == null ||
        !key.isUsable ||
        prompt.trim().isEmpty)
      return;
    final op = ++_operation;
    state = const ImageGenerationState(busy: true);
    try {
      final result = await client.inpaint(
        imagePath: imagePath,
        maskPath: maskPath,
        prompt: prompt,
        token: key.token,
      );
      if (!_active(op)) return;
      state = ImageGenerationState(
        busy: true,
        cached: result.cached,
        images: result.sources.map((s) => GeneratedImage(source: s)).toList(),
      );
      for (var i = 0; i < result.sources.length; i++) await _read(i, op);
      if (_active(op))
        state = ImageGenerationState(
          images: state.images,
          cached: result.cached,
        );
    } catch (_) {
      if (_active(op)) state = const ImageGenerationState(error: '局部重绘失败');
    }
  }

  Future<void> reload(int index) async {
    if (!mounted || state.busy || state.saving != null) return;
    if (index < 0 || index >= state.images.length) return;
    final op = ++_operation;
    state = ImageGenerationState(
      images: state.images,
      cached: state.cached,
      busy: true,
    );
    await _read(index, op);
    if (_active(op)) {
      state = ImageGenerationState(images: state.images, cached: state.cached);
    }
  }

  Future<void> save(int index) async {
    if (!mounted || state.busy || state.saving != null) return;
    if (index < 0 || index >= state.images.length) return;
    final image = state.images[index];
    if (image.bytes == null) return;
    final op = _operation;
    state = ImageGenerationState(
      images: state.images,
      cached: state.cached,
      saving: index,
    );
    try {
      final path = await client.save(image.bytes!, () => _active(op));
      if (!_active(op)) return;
      state = ImageGenerationState(
        cached: state.cached,
        images: [...state.images]
          ..[index] = GeneratedImage(
            source: image.source,
            bytes: image.bytes,
            savedPath: path,
          ),
      );
    } catch (_) {
      if (_active(op)) {
        state = ImageGenerationState(
          images: state.images,
          cached: state.cached,
          error: '保存失败，图片预览已保留',
        );
      }
    }
  }
}

final imageGenerationControllerProvider =
    StateNotifierProvider.autoDispose<
      ImageGenerationController,
      ImageGenerationState
    >((ref) {
      ref.watch(
        authControllerProvider.select((s) => s.session?.accessTokenRef),
      );
      ref.watch(apiBaseUrlProvider);
      return ImageGenerationController(
        ImageGenerationClient(ref.watch(authenticatedClientProvider)),
      );
    });
