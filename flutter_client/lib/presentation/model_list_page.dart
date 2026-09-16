import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/auth_controller.dart';
import '../infrastructure/model/model_client.dart';

class ModelListPage extends ConsumerStatefulWidget {
  const ModelListPage({super.key});
  @override
  ConsumerState<ModelListPage> createState() => _ModelListPageState();
}

class _ModelListPageState extends ConsumerState<ModelListPage> {
  List models = const [];
  String? error;
  bool loading = true;
  bool _fetching = false;
  // Bumped on account change so the previous account's in-flight load neither
  // blocks the new one nor writes its models into the new account's state.
  int _epoch = 0;
  @override
  void initState() {
    super.initState();
    Future.microtask(load);
  }

  void _resetAccount() {
    _epoch++;
    _fetching = false;
    setState(() {
      models = const [];
      error = null;
      loading = true;
    });
    load();
  }

  Future<void> load() async {
    if (_fetching) return;
    final epoch = _epoch;
    _fetching = true;
    setState(() => loading = true);
    try {
      final result = await ModelClient(
        ref.read(authenticatedClientProvider),
      ).list();
      if (!mounted || epoch != _epoch) return;
      setState(() {
        models = result;
        error = null;
        loading = false;
      });
    } catch (e) {
      if (!mounted || epoch != _epoch) return;
      setState(() {
        error = '$e';
        loading = false;
      });
    } finally {
      if (epoch == _epoch) _fetching = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(
      authControllerProvider.select((s) => s.session?.accessTokenRef),
      (_, __) => _resetAccount(),
    );
    ref.listen(apiBaseUrlProvider, (_, __) => _resetAccount());
    return Scaffold(
      appBar: AppBar(
        title: const Text('模型列表'),
        actions: [
          IconButton(
            onPressed: loading ? null : load,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : error != null
          ? Center(child: Text(error!))
          : ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: models.length,
              itemBuilder: (_, i) {
                final model = models[i];
                return Card(
                  child: ListTile(
                    title: Text(model.name),
                    subtitle: Text(
                      '${model.description}\n${model.capabilities.join(' · ')}',
                    ),
                    isThreeLine: true,
                    trailing: model.isDefault
                        ? const Chip(label: Text('默认'))
                        : null,
                  ),
                );
              },
            ),
    );
  }
}
