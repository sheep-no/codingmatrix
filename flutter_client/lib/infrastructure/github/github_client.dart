import '../auth/authenticated_client.dart';
import '../../domain/models/github_binding.dart';

class GithubClient {
  GithubClient(this.api);
  final AuthenticatedClient api;

  Future<GithubBinding> load() async => GithubBinding.fromJson(
    Map<String, dynamic>.from(
      await api.requestJson('/api/v1/github/config') as Map,
    ),
  );

  Future<GithubBinding> save({
    required String username,
    required String token,
    required bool useGithub,
  }) async {
    final result = await api.requestJson(
      '/api/v1/github/config',
      method: 'POST',
      body: {'username': username, 'token': token, 'use_github': useGithub},
    );
    if (result is! Map || result['success'] != true) {
      throw StateError('GitHub 配置保存失败');
    }
    return GithubBinding.fromJson(Map<String, dynamic>.from(result));
  }

  Future<Map<String, dynamic>> saveProject({
    required String projectName,
    required String projectDescription,
    required String projectData,
    required GithubConfigData config,
  }) async => Map<String, dynamic>.from(
    await api.requestJson(
          '/api/v1/github/save',
          method: 'POST',
          body: {
            'project_name': projectName,
            'project_description': projectDescription,
            'project_data': projectData,
            'github_config': {
              'username': config.username,
              'token': config.token,
              'use_github': config.useGithub,
            },
          },
        )
        as Map,
  );

  Future<Map<String, dynamic>> verify() async => Map<String, dynamic>.from(
    await api.requestJson('/api/v1/github/verify', method: 'POST') as Map,
  );

  Future<List<GithubRepo>> listRepos() async {
    final result = await api.requestJson('/api/v1/github/repos');
    final repos = result is Map ? result['repos'] : null;
    return [
      for (final item in repos is List ? repos : const [])
        if (item is Map)
          GithubRepo.fromJson(Map<String, dynamic>.from(item)),
    ];
  }

  Future<List<GithubBranch>> listBranches(String owner, String repo) async {
    final result = await api.requestJson(
      '/api/v1/github/repos/${Uri.encodeComponent(owner)}/${Uri.encodeComponent(repo)}/branches',
    );
    final branches = result is Map ? result['branches'] : null;
    return [
      for (final item in branches is List ? branches : const [])
        if (item is Map)
          GithubBranch.fromJson(Map<String, dynamic>.from(item)),
    ];
  }

  Future<List<GithubCommit>> listCommits(
    String owner,
    String repo, {
    String? sha,
  }) async {
    final query = sha == null || sha.isEmpty
        ? ''
        : '?sha=${Uri.encodeQueryComponent(sha)}';
    final result = await api.requestJson(
      '/api/v1/github/repos/${Uri.encodeComponent(owner)}/${Uri.encodeComponent(repo)}/commits$query',
    );
    final commits = result is Map ? result['commits'] : null;
    return [
      for (final item in commits is List ? commits : const [])
        if (item is Map)
          GithubCommit.fromJson(Map<String, dynamic>.from(item)),
    ];
  }

}

class GithubConfigData {
  const GithubConfigData({
    required this.username,
    required this.token,
    required this.useGithub,
  });
  final String username, token;
  final bool useGithub;
}
