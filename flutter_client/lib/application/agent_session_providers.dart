import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'auth_controller.dart';
import '../infrastructure/agent/agent_session_client.dart';

final agentSessionClientProvider = Provider(
  (ref) => AgentSessionClient(ref.watch(authenticatedClientProvider)),
);

final agentSessionsProvider = FutureProvider.autoDispose((ref) {
  final account = ref.watch(
    authControllerProvider.select((s) => s.session?.accessTokenRef),
  );
  if (account == null) return Future.value(<AgentSession>[]);
  return ref.watch(agentSessionClientProvider).list();
});

final agentSessionDetailProvider = FutureProvider.autoDispose
    .family<AgentSession, String>((ref, id) {
      final account = ref.watch(
        authControllerProvider.select((s) => s.session?.accessTokenRef),
      );
      if (account == null) throw StateError('请重新登录');
      return ref.watch(agentSessionClientProvider).detail(id);
    });
