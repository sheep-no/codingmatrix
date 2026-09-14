import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../application/auth_controller.dart';
import '../infrastructure/agent/agent_project_client.dart';
import '../application/github_controller.dart';
import '../infrastructure/github/github_client.dart';
import '../domain/models/github_binding.dart';
import 'github_settings_page.dart';

final agentProjectClientProvider = Provider<AgentProjectClient>(
  (ref) => AgentProjectClient(ref.watch(authenticatedClientProvider)),
);

class ProjectFilesPage extends ConsumerStatefulWidget {
  const ProjectFilesPage({super.key, required this.project});
  final String project;
  @override
  ConsumerState<ProjectFilesPage> createState() => _ProjectFilesPageState();
}

class _ProjectFilesPageState extends ConsumerState<ProjectFilesPage> {
  List<String> paths = [];
  bool loading = true;
  bool downloading = false;
  String? error;
  String? downloadError;
  String? savedPath;
  bool githubSaving = false;
  String? githubMessage;
  String? githubError;
  GithubBinding? githubBinding;
  int bytes = 0;
  int request = 0;

  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      load();
      loadGithub();
    });
  }

  Future<void> load() async {
    if (!mounted) return;
    final version = ++request;
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final result = await ref
          .read(agentProjectClientProvider)
          .files(widget.project);
      if (mounted && request == version) {
        setState(() {
          paths = result;
          loading = false;
        });
      }
    } catch (_) {
      if (mounted && request == version) {
        setState(() {
          loading = false;
          error = '文件列表加载失败，请重试';
        });
      }
    }
  }

  Future<void> loadGithub() async {
    try {
      final binding = await ref.read(githubClientProvider).load();
      if (mounted) setState(() => githubBinding = binding);
    } catch (_) {
      if (mounted) setState(() => githubBinding = null);
    }
  }

  Future<void> openGithubSettings() async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const GithubSettingsPage()),
    );
    if (mounted) await loadGithub();
  }

  Future<void> download() async {
    setState(() {
      downloading = true;
      bytes = 0;
      downloadError = null;
      savedPath = null;
    });
    try {
      final path = await ref.read(agentProjectClientProvider).download(
        widget.project,
        (count) {
          if (mounted) setState(() => bytes = count);
        },
        active: () => mounted,
      );
      if (mounted) setState(() => savedPath = path);
    } catch (_) {
      if (mounted) setState(() => downloadError = '下载未完成，请重试；单个项目包上限 200 MB');
    } finally {
      if (mounted) setState(() => downloading = false);
    }
  }

  Future<void> pushToGithub() async {
    if (githubSaving || paths.isEmpty || githubBinding?.useGithub != true) return;
    setState(() {
      githubSaving = true;
      githubError = null;
      githubMessage = null;
    });
    try {
      if (paths.length > 200) {
        throw StateError('too many files');
      }
      final files = <String, String>{};
      final client = ref.read(agentProjectClientProvider);
      for (final path in paths) {
        if (path.contains('..') || path.startsWith('/')) continue;
        files[path] = await client.read(widget.project, path);
      }
      if (files.isEmpty) throw StateError('no files');
      final result = await ref.read(githubClientProvider).saveProject(
        projectName: githubRepoNameFromProject(widget.project),
        projectDescription: '',
        projectData: jsonEncode(files),
      );
      if (!mounted) return;
      setState(() {
        githubMessage =
            result['repo_url'] as String? ??
            result['message'] as String? ??
            '已保存';
      });
    } catch (_) {
      if (mounted) {
        setState(() => githubError = 'GitHub 推送失败，请先在设置中保存并启用凭据');
      }
    } finally {
      if (mounted) setState(() => githubSaving = false);
    }
  }

  List<Widget> tree(List<String> entries, [String prefix = '']) {
    final groups = <String, List<String>>{};
    for (final path in entries) {
      final rest = path.substring(prefix.length);
      final name = rest.split('/').first;
      groups.putIfAbsent(name, () => []).add(path);
    }
    return groups.entries.map((group) {
      final path = '$prefix${group.key}';
      if (group.value.any((value) => value.startsWith('$path/'))) {
        return ExpansionTile(
          key: PageStorageKey(path),
          title: Text(group.key),
          leading: const Icon(Icons.folder_outlined),
          children: tree(group.value, '$path/'),
        );
      }
      return ListTile(
        title: Text(group.key),
        leading: const Icon(Icons.description_outlined),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) =>
                _FilePreviewPage(project: widget.project, path: path),
          ),
        ),
      );
    }).toList();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('项目文件'),
      actions: [
        IconButton(
          tooltip: '刷新文件',
          onPressed: loading ? null : load,
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(widget.project),
              FilledButton.icon(
                onPressed: downloading ? null : download,
                icon: const Icon(Icons.download),
                label: Text(downloading ? '已下载 $bytes 字节' : '下载 ZIP 到应用文档'),
              ),
              if (savedPath != null) SelectableText('已保存：$savedPath'),
              if (downloadError != null)
                Text(
                  downloadError!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              if (githubBinding?.useGithub == true)
                FilledButton.icon(
                  key: const Key('githubSaveProject'),
                  onPressed: githubSaving || loading || paths.isEmpty
                      ? null
                      : pushToGithub,
                  icon: const Icon(Icons.cloud_upload_outlined),
                  label: Text(githubSaving ? '正在推送到 GitHub' : '推送到 GitHub'),
                )
              else
                TextButton(
                  key: const Key('githubSettingsFromFiles'),
                  onPressed: openGithubSettings,
                  child: Text(
                    githubBinding == null
                        ? 'GitHub 配置未加载，前往设置'
                        : '未启用 GitHub 保存，前往设置',
                  ),
                ),
              if (githubMessage != null) SelectableText(githubMessage!),
              if (githubError != null)
                Text(
                  githubError!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
            ],
          ),
        ),
        if (loading) const LinearProgressIndicator(),
        if (error != null) TextButton(onPressed: load, child: Text(error!)),
        if (!loading && error == null && paths.isEmpty)
          const Text('项目暂未返回可预览文件。'),
        Expanded(child: ListView(children: tree(paths))),
      ],
    ),
  );
}

class _FilePreviewPage extends ConsumerStatefulWidget {
  const _FilePreviewPage({required this.project, required this.path});
  final String project;
  final String path;
  @override
  ConsumerState<_FilePreviewPage> createState() => _FilePreviewPageState();
}

class _FilePreviewPageState extends ConsumerState<_FilePreviewPage> {
  Future<String>? content;
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    content ??= ref
        .read(agentProjectClientProvider)
        .read(widget.project, widget.path);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(widget.path)),
    body: FutureBuilder<String>(
      future: content,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return Center(
            child: TextButton(
              onPressed: () => setState(
                () => content = ref
                    .read(agentProjectClientProvider)
                    .read(widget.project, widget.path),
              ),
              child: const Text('文件读取失败，点击重试'),
            ),
          );
        }
        return SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: SelectableText(
            snapshot.data ?? '',
            style: const TextStyle(fontFamily: 'monospace'),
          ),
        );
      },
    ),
  );
}
