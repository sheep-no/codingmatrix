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
