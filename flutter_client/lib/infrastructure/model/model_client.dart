import '../../domain/models/model_info.dart';
import '../auth/authenticated_client.dart';

class ModelClient {
  ModelClient(this.api);
  final AuthenticatedClient api;
  Future<List<ModelInfo>> list() async {
    final data = await api.requestJson('/api/v1/models/');
    return [
      for (final item in (data as Map)['models'] as List)
        ModelInfo.fromJson(Map<String, dynamic>.from(item)),
    ];
  }
}
