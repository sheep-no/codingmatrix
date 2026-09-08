import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import '../../domain/models/image_generation.dart';
import '../auth/authenticated_client.dart';

class ImageGenerationClient {
  ImageGenerationClient(this.api, {Future<Directory> Function()? directory})
    : directory = directory ?? getApplicationDocumentsDirectory;
  final AuthenticatedClient api;
  final Future<Directory> Function() directory;
  static const maxBytes = 20 * 1024 * 1024;

  Future<ImageGenerationResult> generate(
    ImageGenerationInput input,
    String token,
  ) async {
    if (!input.valid || token.isEmpty) throw StateError('参数或授权无效');
    final result = await api.requestJson(
      '/api/v1/kolors/text-to-image',
      method: 'POST',
      body: input.toJson(token),
    );
    if (result is! Map || result['success'] != true) throw StateError('生成失败');
    final images = result['images'];
    final sources = images is List && images.isNotEmpty
        ? images
        : result['paths'];
    if (sources is! List ||
        sources.isEmpty ||
        sources.length > 4 ||
        sources.any((e) => e is! String || e.isEmpty)) {
      throw StateError('图片结果无效');
    }
    return ImageGenerationResult(
      List<String>.from(sources),
      result['cached'] == true,
    );
  }

  Future<Uint8List> read(String source) async {
    if (source.startsWith('data:image/')) {
      if (source.length > maxBytes * 4 ~/ 3 + 128) throw StateError('图片过大');
      final data = UriData.parse(source);
      if (!['image/png', 'image/jpeg', 'image/webp'].contains(data.mimeType)) {
        throw StateError('不支持的图片格式');
      }
      final bytes = data.contentAsBytes();
      if (bytes.isEmpty || bytes.length > maxBytes) throw StateError('图片大小无效');
      return bytes;
    }
    // Cached results are server filesystem paths, never client filesystem paths.
    final uri = Uri.tryParse(source);
    if (uri == null ||
        uri.hasScheme ||
        source.contains('..') ||
        source.contains('\\')) {
      throw StateError('不支持的图片地址');
    }
    final name = source.split('/').last;
    if (!RegExp(r'^[A-Za-z0-9_-]+\.(png|jpg|jpeg|webp)$').hasMatch(name)) {
      throw StateError('图片地址无效');
    }
    final response = await api.send(
      http.Request(
        'GET',
        Uri.parse(
          api.auth.baseUrl,
        ).resolve('/api/v1/kolors/resources/${Uri.encodeComponent(name)}'),
      ),
    );
    if ((response.contentLength ?? 0) > maxBytes) {
      await response.stream.take(0).drain<void>();
      throw StateError('图片过大');
    }
    final bytes = BytesBuilder(copy: false);
    await for (final chunk in response.stream) {
      if (bytes.length + chunk.length > maxBytes) throw StateError('图片过大');
      bytes.add(chunk);
    }
    if (bytes.length == 0) throw StateError('图片为空');
    return bytes.takeBytes();
  }

  Future<String> save(Uint8List bytes, bool Function() active) async {
    final folder = await directory();
    if (!active()) throw StateError('操作已失效');
    final extension = bytes.length > 2 && bytes[0] == 0xff
        ? 'jpg'
        : bytes.length > 12 &&
              ascii.decode(bytes.sublist(8, 12), allowInvalid: true) == 'WEBP'
        ? 'webp'
        : 'png';
    final file = File(
      '${folder.path}/image-${DateTime.now().microsecondsSinceEpoch}.$extension',
    );
    await file.writeAsBytes(bytes, flush: true);
    return file.path;
  }
}
