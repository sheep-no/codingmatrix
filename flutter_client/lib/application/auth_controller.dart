import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import '../domain/models/auth_session.dart';
import '../infrastructure/auth/cloud_auth_client.dart';
import '../infrastructure/auth/credential_store.dart';

class AuthState {
  const AuthState({
    this.session,
    this.errorMessage,
    this.isLoading = false,
  });

  final AuthSession? session;
  final String? errorMessage;
  final bool isLoading;

  bool get isAuthenticated => session != null;

  AuthState copyWith({
    AuthSession? session,
    String? errorMessage,
    bool? isLoading,
    bool clearSession = false,
    bool clearError = false,
  }) {
    return AuthState(
      session: clearSession ? null : (session ?? this.session),
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
      isLoading: isLoading ?? this.isLoading,
    );
  }
}

class AuthController extends StateNotifier<AuthState> {
  AuthController(this._client, this._store, {AuthSession? session})
      : super(AuthState(session: session));

  final CloudAuthClient _client;
  final CredentialStore _store;

  Future<void> login({
    required String email,
    required String password,
  }) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final session = await _client.login(email: email, password: password);
      state = AuthState(session: session);
    } on CloudAuthException catch (error) {
      state = AuthState(errorMessage: error.message);
    } catch (error) {
      state = AuthState(errorMessage: error.toString());
    }
  }

  void logout() {
    final ref = state.session?.accessTokenRef;
    if (ref != null) {
      _store.delete(ref);
    }
    state = const AuthState();
  }
}

final credentialStoreProvider = Provider<CredentialStore>((ref) {
  return CredentialStore();
});

final httpClientProvider = Provider<http.Client>((ref) {
  final client = http.Client();
  ref.onDispose(client.close);
  return client;
});

final apiBaseUrlProvider = StateProvider<String>((ref) {
  return 'http://127.0.0.1:8080';
});

final cloudAuthClientProvider = Provider<CloudAuthClient>((ref) {
  return CloudAuthClient(
    baseUrl: ref.watch(apiBaseUrlProvider),
    httpClient: ref.watch(httpClientProvider),
    credentialStore: ref.watch(credentialStoreProvider),
  );
});

final authControllerProvider =
    StateNotifierProvider<AuthController, AuthState>((ref) {
  return AuthController(
    ref.watch(cloudAuthClientProvider),
    ref.watch(credentialStoreProvider),
  );
});
