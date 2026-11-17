import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../infrastructure/provider/dynamic_provider_client.dart';
import '../infrastructure/provider/provider_key_client.dart';
import 'auth_controller.dart';

/// Whether the signed-in account has any model service the server can route to.
///
/// A usable account needs either an enabled dynamic provider or a usable
/// provider key, so both stores are probed. `known` stays false only when both
/// probes fail, so a network problem never becomes "model service missing".
class ModelServiceStatus {
  const ModelServiceStatus({required this.configured, required this.known});

  final bool configured;
  final bool known;
}

final modelServiceStatusProvider =
    FutureProvider.autoDispose<ModelServiceStatus>((ref) async {
      ref.watch(
        authControllerProvider.select((auth) => auth.session?.accessTokenRef),
      );
      final api = ref.watch(authenticatedClientProvider);
      var known = false;
      var configured = false;
      try {
        final providers = await DynamicProviderClient(api).list();
        known = true;
        configured = providers.any((provider) => provider.enabled);
      } catch (_) {
        // Fall through to the key store; one working probe is enough.
      }
      if (!configured) {
        try {
          final keys = await ProviderKeyClient(api).list();
          known = true;
          configured = keys.any((key) => key.isUsable);
        } catch (_) {
          // Keep `known` unchanged so an unreachable key store is not reported
          // as a missing configuration.
        }
      }
      return ModelServiceStatus(configured: configured, known: known);
    });
