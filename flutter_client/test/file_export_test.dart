import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:codingmatrix_desktop/infrastructure/export/file_exporter.dart';
import 'package:codingmatrix_desktop/presentation/saved_file_actions.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// A picker that records what it was handed and returns a canned destination.
class RecordingPicker {
  RecordingPicker({this.target});
  final String? target;
  int calls = 0;
  String? lastName;
  Uint8List? lastBytes;

  Future<String?> call({String? fileName, Uint8List? bytes}) async {
    calls++;
    lastName = fileName;
    lastBytes = bytes;
    return target;
  }
}

Future<File> sourceFile({int bytes = 8}) async {
  final dir = await Directory('/tmp/opencode').createTemp('file-export-');
  final file = File('${dir.path}/artifact.bin');
  await file.writeAsBytes(List<int>.generate(bytes, (i) => i), flush: true);
  return file;
}

FileExporter exporterFor(
  RecordingPicker picker, {
  bool mobile = false,
  int maxMobileBytes = 128 * 1024 * 1024,
}) => FileExporter(
  picker: picker.call,
  isMobile: () => mobile,
  maxMobileBytes: maxMobileBytes,
);

/// Skips file IO so widget tests stay inside the fake-async zone.
class FakeExporter extends FileExporter {
  FakeExporter(this.onSave);
  final Future<String?> Function(String path) onSave;
  @override
  Future<String?> save(String sourcePath) => onSave(sourcePath);
}

void main() {
  test('桌面端把源文件复制到用户选择的位置', () async {
    final source = await sourceFile();
    final dir = await Directory('/tmp/opencode').createTemp('file-export-dst-');
    final target = '${dir.path}/artifact.bin';
    final picker = RecordingPicker(target: target);

    final saved = await exporterFor(picker).save(source.path);

    expect(saved, target);
    expect(await File(target).readAsBytes(), await source.readAsBytes());
    // Desktop lets the picker write the file, so it must not receive bytes.
    expect(picker.lastBytes, isNull);
    expect(picker.lastName, 'artifact.bin');
  });

  test('桌面端取消选择时不复制文件', () async {
    final source = await sourceFile();
    final picker = RecordingPicker();

    expect(await exporterFor(picker).save(source.path), isNull);
    expect(picker.calls, 1);
    expect(picker.lastBytes, isNull);
  });

  test('移动端把字节交给选择器而不做复制', () async {
    final source = await sourceFile(bytes: 6);
    final picker = RecordingPicker(target: '/storage/emulated/0/artifact.bin');

    final saved = await exporterFor(picker, mobile: true).save(source.path);

    expect(saved, '/storage/emulated/0/artifact.bin');
    expect(picker.lastBytes, await source.readAsBytes());
    expect(picker.lastName, 'artifact.bin');
  });

  test('移动端超出上限时拒绝导出且不调用选择器', () async {
    final source = await sourceFile(bytes: 32);
    final picker = RecordingPicker(target: '/storage/emulated/0/artifact.bin');
    final exporter = exporterFor(picker, mobile: true, maxMobileBytes: 16);

    await expectLater(
      exporter.save(source.path),
      throwsA(
        isA<FileExportException>().having(
          (e) => e.message,
          'message',
          contains('文件过大'),
        ),
      ),
    );
    expect(picker.calls, 0);
  });

  test('源文件不存在时抛出可读错误', () async {
    final picker = RecordingPicker(target: '/tmp/opencode/missing.bin');

    await expectLater(
      exporterFor(picker).save('/tmp/opencode/definitely-missing.bin'),
      throwsA(
        isA<FileExportException>().having(
          (e) => e.message,
          'message',
          contains('源文件不存在'),
        ),
      ),
    );
    expect(picker.calls, 0);
  });

  testWidgets('导出成功后展示目标路径', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          fileExporterProvider.overrideWithValue(
            FakeExporter((_) async => '/tmp/opencode/artifact.bin'),
          ),
        ],
        child: const MaterialApp(
          home: Scaffold(
            body: SavedFileActions(path: '/tmp/opencode/artifact.bin'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('导出到...'));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('已导出到'), findsOneWidget);
    expect(find.textContaining('artifact.bin'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('取消导出时不报错并提示已取消', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          fileExporterProvider.overrideWithValue(
            FakeExporter((_) async => null),
          ),
        ],
        child: const MaterialApp(
          home: Scaffold(
            body: SavedFileActions(path: '/tmp/opencode/artifact.bin'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('导出到...'));
    await tester.pump();
    await tester.pump();
    expect(find.text('已取消导出'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('导出进行中禁止重复点击', (tester) async {
    final gate = Completer<String?>();
    var calls = 0;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          fileExporterProvider.overrideWithValue(
            FakeExporter((_) {
              calls++;
              return gate.future;
            }),
          ),
        ],
        child: const MaterialApp(
          home: Scaffold(
            body: SavedFileActions(path: '/tmp/opencode/artifact.bin'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('导出到...'));
    await tester.pump();
    expect(find.text('导出中...'), findsOneWidget);
    // TextButton.icon builds a private subtype, so target the icon instead.
    await tester.tap(find.byIcon(Icons.save_alt), warnIfMissed: false);
    await tester.pump();
    expect(calls, 1);
    gate.complete('/tmp/opencode/artifact.bin');
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('已导出到'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('导出失败时展示错误原文', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          fileExporterProvider.overrideWithValue(
            FakeExporter(
              (_) async => throw const FileExportException('源文件不存在，请重新下载'),
            ),
          ),
        ],
        child: const MaterialApp(
          home: Scaffold(
            body: SavedFileActions(path: '/tmp/opencode/artifact.bin'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('导出到...'));
    await tester.pump();
    await tester.pump();
    expect(find.text('源文件不存在，请重新下载'), findsOneWidget);
    expect(find.text('导出中...'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
