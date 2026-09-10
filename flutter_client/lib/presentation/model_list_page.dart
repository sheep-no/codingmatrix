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
  @override
  void initState() {
    super.initState();
    Future.microtask(load);
  }

  Future<void> load() async {
    setState(() => loading = true);
    try {
      final result = await ModelClient(
        ref.read(authenticatedClientProvider),
      ).list();
      if (mounted) {
        setState(() {
          models = result;
          error = null;
          loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          error = '$e';
          loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
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
