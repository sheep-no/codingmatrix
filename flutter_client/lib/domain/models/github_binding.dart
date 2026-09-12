class GithubBinding {
  const GithubBinding({
    this.username = '',
    this.useGithub = false,
    this.verified = false,
    this.persisted = false,
    this.hasToken = false,
    this.credentialState = 'unknown',
  });

  factory GithubBinding.fromJson(Map<String, dynamic> json) => GithubBinding(
    username: json['username'] as String? ?? '',
    useGithub: json['use_github'] == true,
    verified: json['verified'] == true,
    persisted: json['persisted'] == true,
    hasToken: json['has_token'] == true,
    credentialState: json['credential_state'] as String? ?? 'unknown',
  );

  final String username;
  // Legacy callers may read an empty token; responses never enter UI state.
  String get token => '';
  final bool useGithub;
  final bool verified;
  final bool persisted, hasToken;
  final String credentialState;

  bool get configured => persisted && username.isNotEmpty && hasToken;
}

class GithubRepo {
  const GithubRepo({
    required this.fullName,
    required this.name,
    required this.owner,
    this.private = false,
    this.defaultBranch = 'main',
    this.htmlUrl = '',
    this.description = '',
  });

  factory GithubRepo.fromJson(Map<String, dynamic> json) => GithubRepo(
    fullName: json['full_name'] as String? ?? '',
    name: json['name'] as String? ?? '',
    owner: json['owner'] as String? ?? '',
    private: json['private'] == true,
    defaultBranch: json['default_branch'] as String? ?? 'main',
    htmlUrl: json['html_url'] as String? ?? '',
    description: json['description'] as String? ?? '',
  );

  final String fullName, name, owner, defaultBranch, htmlUrl, description;
  final bool private;
}

class GithubBranch {
  const GithubBranch({
    required this.name,
    this.sha = '',
    this.protected = false,
  });

  factory GithubBranch.fromJson(Map<String, dynamic> json) => GithubBranch(
    name: json['name'] as String? ?? '',
    sha: json['sha'] as String? ?? '',
    protected: json['protected'] == true,
  );

  final String name, sha;
  final bool protected;
}

class GithubCommit {
  const GithubCommit({
    required this.sha,
    this.message = '',
    this.author = '',
    this.date = '',
    this.htmlUrl = '',
  });

  factory GithubCommit.fromJson(Map<String, dynamic> json) => GithubCommit(
    sha: json['sha'] as String? ?? '',
    message: json['message'] as String? ?? '',
    author: json['author'] as String? ?? '',
    date: json['date'] as String? ?? '',
    htmlUrl: json['html_url'] as String? ?? '',
  );

  final String sha, message, author, date, htmlUrl;
}
