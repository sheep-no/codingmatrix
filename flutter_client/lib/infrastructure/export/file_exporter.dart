import 'dart:io';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Raised when a saved artifact cannot be exported to a user-chosen location.
class FileExportException implements Exception {
  const FileExportException(this.message);
  final String message;
  @override
  String toString() => message;
}

typedef SaveFilePicker =
    Future<String?> Function({String? fileName, Uint8List? bytes});

/// Copies an artifact the app wrote into its private documents directory to a
/// location the user picks.
///
/// Android has no user-visible app directory, so a downloaded file stays
/// unreachable without the SAF picker behind [FilePicker.saveFile]. Desktop
/// picks a path and the bytes are copied there.
class FileExporter {
  FileExporter({
    SaveFilePicker? picker,
    bool Function()? isMobile,
    this.maxMobileBytes = 128 * 1024 * 1024,
  }) : _picker = picker ?? _defaultPicker,
       _isMobile = isMobile ?? _defaultIsMobile;

  final SaveFilePicker _picker;
  final bool Function() _isMobile;
  // Android/iOS hand the whole payload to the picker in one buffer, so a very
  // large artifact would risk an OOM on a phone.
  final int maxMobileBytes;

  static Future<String?> _defaultPicker({String? fileName, Uint8List? bytes}) =>
      FilePicker.platform.saveFile(fileName: fileName, bytes: bytes);

  static bool _defaultIsMobile() => Platform.isAndroid || Platform.isIOS;

  /// Returns the chosen destination, or null when the user cancelled.
  Future<String?> save(String sourcePath) async {
    final file = File(sourcePath);
    if (!await file.exists()) {
      throw const FileExportException('源文件不存在，请重新下载');
    }
    final name = sourcePath.split(RegExp(r'[\\/]')).last;
    if (_isMobile()) {
      if (await file.length() > maxMobileBytes) {
        throw const FileExportException('文件过大，无法导出到所选位置');
      }
      return _picker(fileName: name, bytes: await file.readAsBytes());
    }
    final target = await _picker(fileName: name);
    if (target == null) return null;
    return (await file.copy(target)).path;
  }
}

final fileExporterProvider = Provider<FileExporter>((ref) => FileExporter());
