/// Authenticated cloud session. The access token stays in CredentialStore.
class AuthSession {
  const AuthSession({
    required this.username,
    required this.permissionLevel,
    required this.accessTokenRef,
    this.tokenType = 'bearer',
  });

  final String username;
  final String permissionLevel;
  final String accessTokenRef;
  final String tokenType;

  Map<String, dynamic> toJson() {
    return {
      'username': username,
      'permission_level': permissionLevel,
      'access_token_ref': accessTokenRef,
      'token_type': tokenType,
    };
  }

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    return AuthSession(
      username: json['username'] as String? ?? '',
      permissionLevel: json['permission_level'] as String? ?? 'normal',
      accessTokenRef: json['access_token_ref'] as String? ?? '',
      tokenType: json['token_type'] as String? ?? 'bearer',
    );
  }
}
