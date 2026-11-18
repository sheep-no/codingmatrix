import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';

class FileShareException implements Exception {
  const FileShareException(this.message);
  final String message;

  @override
  String toString() => message;
}

typedef ShareFile = Future<void> Function(String path, {String? subject});

class FileSharer {
  FileSharer({ShareFile? share}) : _share = share ?? _defaultShare;

  final ShareFile _share;

  static Future<void> _defaultShare(String path, {String? subject}) async {
    final result = await SharePlus.instance.share(
      ShareParams(files: [XFile(path)], subject: subject),
    );
    if (result.status == ShareResultStatus.unavailable) {
      throw const FileShareException('当前设备没有可用的分享方式');
    }
  }

  Future<void> share(String path, {String? subject}) =>
      _share(path, subject: subject);
}

final fileSharerProvider = Provider<FileSharer>((ref) => FileSharer());
