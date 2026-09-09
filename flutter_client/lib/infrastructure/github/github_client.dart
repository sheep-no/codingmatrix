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
}
