import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import '../domain/models/auth_session.dart';
import '../infrastructure/auth/cloud_auth_client.dart';
import '../infrastructure/auth/credential_store.dart';
import '../infrastructure/auth/authenticated_client.dart';

class AuthState {
  const AuthState({
    this.session,
    this.errorMessage,
    this.isLoading = false,
    this.isRestoring = false,
  });

  final AuthSession? session;
  final String? errorMessage;
  final bool isLoading;
  final bool isRestoring;

  bool get isAuthenticated => session != null;

  AuthState copyWith({
    AuthSession? session,
    String? errorMessage,
    bool? isLoading,
    bool? isRestoring,
    bool clearSession = false,
    bool clearError = false,
  }) {
    return AuthState(
      session: clearSession ? null : (session ?? this.session),
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
      isLoading: isLoading ?? this.isLoading,
      isRestoring: isRestoring ?? this.isRestoring,
    );
  }
}

class AuthController extends StateNotifier<AuthState> {
  AuthController(
    this._client,
    CredentialStore store, {
    AuthSession? session,
    this.onBaseUrlChanged,
  })
    : super(AuthState(session: session)) {
    _client.onSessionChanged = (session) {
      if (mounted) {
        state = AuthState(
          session: session,
          isLoading: state.isLoading,
          isRestoring: state.isRestoring,
        );
      }
    };
  }

  final CloudAuthClient _client;
  final void Function(String baseUrl)? onBaseUrlChanged;
  int _operation = 0;

  void _publishBaseUrl() {
    onBaseUrlChanged?.call(_client.baseUrl);
  }

  Future<void> restore() async {
    final operation = ++_operation;
    state = const AuthState(isLoading: true, isRestoring: true);
    try {
      final session = await _client.restore();
      if (mounted && operation == _operation) {
        _publishBaseUrl();
        state = AuthState(session: session);
      }
    } on SecureStorageUnavailableException {
      if (mounted && operation == _operation) {
        state = const AuthState(errorMessage: secureStorageUnavailableMessage);
      }
    } catch (_) {
      if (mounted && operation == _operation) {
        state = const AuthState(errorMessage: '会话恢复失败，请重新登录');
      }
    }
  }

  Future<void> login({
    required String email,
    required String password,
    String? serviceUrl,
  }) async {
    if (state.isLoading) return;
    final operation = ++_operation;
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final session = await _client.login(
        email: email,
        password: password,
        serviceUrl: serviceUrl,
      );
      if (mounted && operation == _operation) {
        _publishBaseUrl();
        state = AuthState(session: session);
      }
    } on CloudAuthException catch (error) {
      if (mounted && operation == _operation) {
        state = AuthState(
          errorMessage: error.secureStorage
              ? secureStorageUnavailableMessage
              : error.message,
        );
      }
    } catch (_) {
      if (mounted && operation == _operation) {
        state = const AuthState(errorMessage: '登录失败，请检查网络连接后重试');
      }
    }
  }

  Future<void> logout() async {
    final operation = ++_operation;
    state = const AuthState(isLoading: true);
    try {
      await _client.logout(revokeRemote: true);
      if (mounted && operation == _operation) state = const AuthState();
    } on SecureStorageUnavailableException {
      // The in-memory session is already cleared; only the stored copy is left.
      if (mounted && operation == _operation) {
        state = const AuthState(errorMessage: '本机安全存储不可用，本地凭据未能清除，请手动处理后重试退出');
      }
    } catch (_) {
      if (mounted && operation == _operation) {
        state = const AuthState(
          errorMessage: '本地安全凭据清除失败，请重试退出',
          isLoading: false,
        );
      }
    }
  }

  @override
  void dispose() {
    _operation++;
    _client.onSessionChanged = null;
    _client.detach();
    super.dispose();
  }
}

final credentialStoreProvider = Provider<CredentialStore>((ref) {
  return CredentialStore(storage: const DeviceSessionStorage());
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
    baseUrl: ref.read(apiBaseUrlProvider),
    httpClient: ref.watch(httpClientProvider),
    credentialStore: ref.watch(credentialStoreProvider),
  );
});

final authControllerProvider = StateNotifierProvider<AuthController, AuthState>(
  (ref) {
    final controller = AuthController(
      ref.watch(cloudAuthClientProvider),
      ref.watch(credentialStoreProvider),
      onBaseUrlChanged: (baseUrl) {
        ref.read(apiBaseUrlProvider.notifier).state = baseUrl;
      },
    );
    controller.restore();
    return controller;
  },
);

final authenticatedClientProvider = Provider<AuthenticatedClient>((ref) {
  return AuthenticatedClient(
    ref.watch(cloudAuthClientProvider),
    ref.watch(httpClientProvider),
  );
});
