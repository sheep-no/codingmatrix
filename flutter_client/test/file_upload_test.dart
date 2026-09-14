import 'dart:async';
import 'dart:io';

import 'package:codingmatrix_desktop/application/auth_controller.dart';
import 'package:codingmatrix_desktop/presentation/file_center_page.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'agent_delivery_test.dart' show DeliveryApi;

class ChunkApi extends DeliveryApi {
  ChunkApi(super.handle);

  final uploaded = <int>[];
  int? failIndex;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final path = request.url.path;
    if (!path.contains('/upload/chunk/')) {
      return super.send(request);
    }
    final index = int.parse(path.split('/').last);
    if (failIndex == index) {
      throw const SocketException('connection lost');
    }
    uploaded.add(index);
    return http.StreamedResponse(const Stream<List<int>>.empty(), 200);
  }
}

Future<File> sampleFile() async {
  final file = File('${Directory.systemTemp.path}/cm_upload_resume.bin');
  await file.writeAsBytes(const [1, 2, 3, 4, 5, 6, 7, 8], flush: true);
  return file;
}

Map<String, dynamic> initResponse({List<int> uploadedChunks = const []}) => {
  'file_id': 'f1',
  'status': 'new',
  'chunk_size': 4,
  'total_chunks': 2,
  'uploaded_chunks': uploadedChunks,
};

Map<String, dynamic> mergeResponse() => {
  'file_id': 'f1',
  'name': 'cm_upload_resume.bin',
  'server_path': 'uploads/cm_upload_resume.bin',
};

class FileApi extends DeliveryApi {
  FileApi() : super((_, _, _) async => null);

  Future<Map<String, dynamic>> Function(String)? upload;

  @override
  Future<Map<String, dynamic>> uploadFile(String path) async {
    return upload == null
        ? {
            'name': 'a.txt',
            'server_path': 'uploads/a.txt',
            'file_id': '1',
          }
        : await upload!(path);
  }

  Future<http.StreamedResponse> Function(http.BaseRequest)? downloadSend;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    if (downloadSend != null) return downloadSend!(request);
    return super.send(request);
  }
}

class TestPicker extends FilePicker {
  FilePickerResult? result;
  Object? error;
  Completer<FilePickerResult?>? pending;

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
    expect(allowMultiple, true);
    return pending?.future ?? result;
  }
}

void main() {
  test('断点续传跳过已上传分片并合并', () async {
    final file = await sampleFile();
    final api = ChunkApi((path, method, body) async {
      expect(method, 'POST');
      if (path.startsWith('/api/v1/files/upload/init')) {
        return initResponse(uploadedChunks: const [0]);
      }
      if (path.startsWith('/api/v1/files/upload/merge/f1')) {
        return mergeResponse();
      }
      fail('unexpected $path');
    });

    final result = await api.uploadFileResumable(file.path);
    expect(api.uploaded, [1]);
    expect(result['server_path'], 'uploads/cm_upload_resume.bin');
    expect(result['file_id'], 'f1');
  });

  test('分片上传网络断开后再次上传从已上传分片续传', () async {
    final file = await sampleFile();
    var attempt = 0;
    final api = ChunkApi((path, method, body) async {
      if (path.startsWith('/api/v1/files/upload/init')) {
        return initResponse(
          uploadedChunks: attempt == 0 ? const [] : const [0],
        );
      }
      if (path.startsWith('/api/v1/files/upload/merge/f1')) {
        return mergeResponse();
      }
      fail('unexpected $path');
    });

    api.failIndex = 1;
    await expectLater(
      api.uploadFileResumable(file.path),
      throwsA(
        isA<SocketException>().having(
          (error) => error.message,
          'message',
          'connection lost',
        ),
      ),
    );
    expect(api.uploaded, [0]);

    attempt = 1;
    api.failIndex = null;
    final result = await api.uploadFileResumable(file.path);
    expect(api.uploaded, [0, 1]);
    expect(result['server_path'], 'uploads/cm_upload_resume.bin');
  });

  testWidgets('文件中心上传中网络断开显示失败', (tester) async {
    final picker = TestPicker()
      ..result = FilePickerResult([
        PlatformFile(name: 'a.txt', path: '/tmp/a.txt', size: 10),
      ]);
    FilePicker.platform = picker;
    final api = FileApi()
      ..upload = (_) async => throw const SocketException('connection lost');
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: FileCenterPage()),
      ),
    );
    await tester.tap(find.text('选择文件上传'));
    await tester.pump();
    expect(find.textContaining('上传失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(find.text('a.txt'), findsNothing);
  });

  testWidgets('文件中心上传中退出再进入不会带回列表', (tester) async {
    final upload = Completer<Map<String, dynamic>>();
    final picker = TestPicker()
      ..result = FilePickerResult([
        PlatformFile(name: 'a.txt', path: '/tmp/a.txt', size: 10),
      ]);
    FilePicker.platform = picker;
    final api = FileApi()..upload = (_) => upload.future;
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: FileCenterPage()),
      ),
    );
    await tester.tap(find.text('选择文件上传'));
    await tester.pump();
    expect(find.text('上传中...'), findsOneWidget);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开文件中心'))),
      ),
    );
    await tester.pump();

    upload.complete({
      'name': 'a.txt',
      'server_path': 'uploads/a.txt',
      'file_id': '1',
    });
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: FileCenterPage()),
      ),
    );
    await tester.pump();
    expect(find.text('离开文件中心'), findsNothing);
    expect(find.text('a.txt'), findsNothing);
    expect(find.text('上传完成'), findsNothing);
    expect(find.text('选择文件上传'), findsOneWidget);
  });

  testWidgets('未选择文件不会上传', (tester) async {
    var uploads = 0;
    FilePicker.platform = TestPicker();
    final api = FileApi()
      ..upload = (_) async {
        uploads += 1;
        return {
          'name': 'a.txt',
          'server_path': 'uploads/a.txt',
          'file_id': '1',
        };
      };
    await tester.pumpWidget(
      ProviderScope(
        overrides: [authenticatedClientProvider.overrideWithValue(api)],
        child: const MaterialApp(home: FileCenterPage()),
      ),
    );
    await tester.tap(find.text('选择文件上传'));
    await tester.pump();
    expect(uploads, 0);
    expect(find.text('上传完成'), findsNothing);
  });

  testWidgets('选择文件失败显示失败原文', (tester) async {
    FilePicker.platform = TestPicker()
      ..error = const SocketException('connection lost');
    var uploads = 0;
    final api = FileApi()
      ..upload = (_) async {
        uploads += 1;
        return {
          'name': 'a.txt',
          'server_path': 'uploads/a.txt',
          'file_id': '1',
        };
      };
    await tester.pumpWidget(
      ProviderScope(
        overrides: [authenticatedClientProvider.overrideWithValue(api)],
        child: const MaterialApp(home: FileCenterPage()),
      ),
    );
    await tester.tap(find.text('选择文件上传'));
    await tester.pump();
    expect(find.textContaining('选择文件失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(uploads, 0);
    expect(find.text('上传中...'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('选择文件后离开页面不再对已销毁状态设值', (tester) async {
    final picker = TestPicker()..pending = Completer<FilePickerResult?>();
    FilePicker.platform = picker;
    final api = FileApi();
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: FileCenterPage()),
      ),
    );
    await tester.tap(find.text('选择文件上传'));
    await tester.pump();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开文件中心'))),
      ),
    );
    await tester.pump();
    picker.pending!.complete(
      FilePickerResult([
        PlatformFile(name: 'a.txt', path: '/tmp/a.txt', size: 10),
      ]),
    );
    await tester.pump();
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('文件中心下载网络断开显示失败', (tester) async {
    FilePicker.platform = TestPicker()
      ..result = FilePickerResult([
        PlatformFile(name: 'a.txt', path: '/tmp/a.txt', size: 10),
      ]);
    final api = FileApi()
      ..downloadSend = (_) async =>
          throw const SocketException('connection lost');
    await tester.pumpWidget(
      ProviderScope(
        overrides: [authenticatedClientProvider.overrideWithValue(api)],
        child: const MaterialApp(home: FileCenterPage()),
      ),
    );
    await tester.tap(find.text('选择文件上传'));
    await tester.pump();
    await tester.pump();
    expect(find.text('a.txt'), findsOneWidget);
    await tester.tap(find.byIcon(Icons.download));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('下载失败'), findsOneWidget);
    expect(find.textContaining('connection lost'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('文件中心下载中退出再进入不会带回列表', (tester) async {
    final pending = Completer<http.StreamedResponse>();
    FilePicker.platform = TestPicker()
      ..result = FilePickerResult([
        PlatformFile(name: 'a.txt', path: '/tmp/a.txt', size: 10),
      ]);
    final api = FileApi()..downloadSend = (_) => pending.future;
    final container = ProviderContainer(
      overrides: [authenticatedClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: FileCenterPage()),
      ),
    );
    await tester.tap(find.text('选择文件上传'));
    await tester.pump();
    await tester.pump();
    expect(find.text('a.txt'), findsOneWidget);
    await tester.tap(find.byIcon(Icons.download));
    await tester.pump();
    expect(find.text('下载中...'), findsOneWidget);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: Text('离开文件中心'))),
      ),
    );
    await tester.pump();
    pending.completeError(const SocketException('connection lost'));
    await tester.pump();
    await tester.pump();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: FileCenterPage()),
      ),
    );
    await tester.pump();
    expect(find.text('a.txt'), findsNothing);
    expect(find.textContaining('下载失败'), findsNothing);
    expect(find.text('选择文件上传'), findsOneWidget);
  });
}
