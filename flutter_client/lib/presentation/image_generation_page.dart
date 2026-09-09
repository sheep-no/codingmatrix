import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/auth_controller.dart';
import '../application/image_generation_controller.dart';
import '../application/provider_key_controller.dart';
import '../domain/models/image_generation.dart';
import 'provider_settings_page.dart';

class ImageGenerationPage extends ConsumerStatefulWidget {
  const ImageGenerationPage({super.key});
  @override
  ConsumerState<ImageGenerationPage> createState() =>
      _ImageGenerationPageState();
}

class _ImageGenerationPageState extends ConsumerState<ImageGenerationPage> {
  final prompt = TextEditingController();
  final negative = TextEditingController();
  final seed = TextEditingController();
  final form = GlobalKey<FormState>();
  int size = 1024, count = 1;
  double steps = 50, guidance = 7.5;
  @override
  void dispose() {
    prompt.dispose();
    negative.dispose();
    seed.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(
      authControllerProvider.select((s) => s.session?.accessTokenRef),
      (_, __) {
        prompt.clear();
        negative.clear();
        seed.clear();
      },
    );
    ref.listen(apiBaseUrlProvider, (_, __) {
      prompt.clear();
      negative.clear();
      seed.clear();
    });
    final state = ref.watch(imageGenerationControllerProvider);
    final key = ref.watch(providerKeyControllerProvider).selected;
    final controller = ref.read(imageGenerationControllerProvider.notifier);
    final enabled = !state.busy && state.saving == null;
    return Scaffold(
      appBar: AppBar(title: const Text('图片生成')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 900),
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text('Kolors 文生图', style: Theme.of(context).textTheme.titleLarge),
              Text(
                key?.provider == 'siliconflow'
                    ? '已选择 SiliconFlow 授权'
                    : '请先选择 SiliconFlow 授权',
              ),
              TextButton(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => const ProviderSettingsPage(),
                  ),
                ),
                child: const Text('管理 Provider 授权'),
              ),
              Form(
                key: form,
                child: Column(
                  children: [
                    TextFormField(
                      key: const Key('imagePrompt'),
                      controller: prompt,
                      enabled: enabled,
                      minLines: 2,
                      maxLines: 5,
                      decoration: const InputDecoration(labelText: '画面描述'),
                      validator: (v) =>
                          v == null || v.trim().isEmpty ? '请输入画面描述' : null,
                    ),
                    TextFormField(
                      controller: negative,
                      enabled: enabled,
                      decoration: const InputDecoration(labelText: '反向提示词（可选）'),
                    ),
                    DropdownButtonFormField<int>(
                      initialValue: size,
                      decoration: const InputDecoration(labelText: '尺寸'),
                      items: [512, 768, 1024]
                          .map(
                            (s) => DropdownMenuItem(
                              value: s,
                              child: Text('$s × $s'),
                            ),
                          )
                          .toList(),
                      onChanged: enabled
                          ? (s) => setState(() => size = s!)
                          : null,
                    ),
                    DropdownButtonFormField<int>(
                      initialValue: count,
                      decoration: const InputDecoration(labelText: '图片数量'),
                      items: [1, 2, 3, 4]
                          .map(
                            (n) =>
                                DropdownMenuItem(value: n, child: Text('$n 张')),
                          )
                          .toList(),
                      onChanged: enabled
                          ? (n) => setState(() => count = n!)
                          : null,
                    ),
                    Text('推理步数 ${steps.round()}'),
                    Slider(
                      value: steps,
                      min: 20,
                      max: 100,
                      divisions: 80,
                      onChanged: enabled
                          ? (v) => setState(() => steps = v)
                          : null,
                    ),
                    Text('引导系数 ${guidance.toStringAsFixed(1)}'),
                    Slider(
                      value: guidance,
                      min: 1,
                      max: 20,
                      divisions: 38,
                      onChanged: enabled
                          ? (v) => setState(() => guidance = v)
                          : null,
                    ),
                    TextFormField(
                      controller: seed,
                      enabled: enabled,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(
                        labelText: '随机种子（留空自动生成）',
                      ),
                      validator: (v) =>
                          v == null ||
                              v.trim().isEmpty ||
                              (int.tryParse(v) != null &&
                                  int.parse(v) >= 0 &&
                                  int.parse(v) <= 2147483647)
                          ? null
                          : '请输入 0 至 2147483647 的整数',
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              FilledButton(
                key: const Key('imageGenerate'),
                onPressed: enabled
                    ? () {
                        if (!form.currentState!.validate()) return;
                        controller.generate(
                          ImageGenerationInput(
                            prompt: prompt.text,
                            negativePrompt: negative.text,
                            width: size,
                            height: size,
                            steps: steps.round(),
                            guidance: guidance,
                            count: count,
                            seed: int.tryParse(seed.text.trim()),
                          ),
                          key,
                        );
                      }
                    : null,
                child: const Text('生成图片'),
              ),
              if (state.busy) ...[
                const LinearProgressIndicator(),
                const Text('正在生成或读取图片，请等待'),
              ],
              if (state.error != null)
                Text(
                  state.error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              if (state.cached) const Text('已读取缓存结果'),
              for (var i = 0; i < state.images.length; i++)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      children: [
                        Text('图片 ${i + 1}'),
                        if (state.images[i].bytes != null)
                          Image.memory(
                            state.images[i].bytes!,
                            height: 320,
                            fit: BoxFit.contain,
                            errorBuilder: (_, __, ___) =>
                                const Text('图片格式无法预览'),
                          ),
                        if (state.images[i].error != null)
                          Text(state.images[i].error!),
                        if (state.images[i].error != null)
                          TextButton(
                            onPressed: enabled
                                ? () => controller.reload(i)
                                : null,
                            child: const Text('重新加载图片'),
                          ),
                        if (state.images[i].bytes != null)
                          TextButton(
                            onPressed: enabled
                                ? () => controller.save(i)
                                : null,
                            child: Text(
                              state.saving == i ? '正在保存' : '保存到应用文档目录',
                            ),
                          ),
                        if (state.images[i].savedPath != null)
                          SelectableText('已保存：${state.images[i].savedPath}'),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
