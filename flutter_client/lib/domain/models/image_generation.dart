import 'dart:typed_data';

class ImageGenerationInput {
  const ImageGenerationInput({
    required this.prompt,
    this.negativePrompt = '',
    this.width = 1024,
    this.height = 1024,
    this.steps = 50,
    this.guidance = 7.5,
    this.count = 1,
    this.seed,
  });
  final String prompt, negativePrompt;
  final int width, height, steps, count;
  final double guidance;
  final int? seed;
  bool get valid =>
      prompt.trim().isNotEmpty &&
      steps >= 20 &&
      steps <= 100 &&
      guidance >= 1 &&
      guidance <= 20 &&
      count >= 1 &&
      count <= 4 &&
      [512, 768, 1024].contains(width) &&
      [512, 768, 1024].contains(height) &&
      (seed == null || (seed! >= 0 && seed! <= 2147483647));
  Map<String, Object?> toJson(String token) => {
    'prompt': prompt.trim(),
    'negative_prompt': negativePrompt.trim(),
    'width': width,
    'height': height,
    'num_inferences': steps,
    'guidance_scale': guidance,
    'num_images': count,
    if (seed != null) 'seed': seed,
    'api_key_token': token,
  };
}

class GeneratedImage {
  const GeneratedImage({
    required this.source,
    this.bytes,
    this.error,
    this.savedPath,
  });
  final String source;
  final Uint8List? bytes;
  final String? error, savedPath;
}

class ImageGenerationResult {
  const ImageGenerationResult(this.sources, this.cached);
  final List<String> sources;
  final bool cached;
}
