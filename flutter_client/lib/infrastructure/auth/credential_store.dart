/// Stores access tokens by opaque reference. Domain objects never hold the token.
class CredentialStore {
  final Map<String, String> _tokens = <String, String>{};
  int _sequence = 0;

  String storeAccessToken(String token) {
    _sequence += 1;
    final ref = 'token-$_sequence';
    _tokens[ref] = token;
    return ref;
  }

  String? read(String accessTokenRef) => _tokens[accessTokenRef];

  void delete(String accessTokenRef) {
    _tokens.remove(accessTokenRef);
  }

  void clear() {
    _tokens.clear();
  }
}
