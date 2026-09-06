"""视觉任务应统一使用 Qwen3.5 作为主模型。"""

import pytest

from app.agent.models import DEFAULT_VISUAL_MODEL, ModelRegistry, ModelRouter, ModelCapability, TaskType
from app.api.v1.Aicode import select_model_for_prompt
from app.utils.aicloud.model_registry import ModelCapability as CloudModelCapability, get_available_models
from app.utils.pptx.visual_analyzer import PPTVisualAnalyzer
from app.utils.vision import IMAGE_DESC_MODEL, VISION_MODEL, VISION_MODEL_FALLBACK, analyze_image
from app.utils.visual.visual_analyzer import VisualAnalyzer


def test_visual_task_routes_to_qwen35():
    model = ModelRouter.route(TaskType.VISUAL_UNDERSTANDING)

    assert model.name == "Qwen/Qwen3.5-4B"
    assert ModelCapability.VISION in model.capabilities
    assert ModelRouter.TASK_MODEL_MAP[TaskType.VISUAL_UNDERSTANDING][0] == "qwen3.5-4b"


def test_image_helpers_use_qwen35_as_visual_default():
    assert VISION_MODEL == "Qwen/Qwen3.5-4B"
    assert IMAGE_DESC_MODEL == "Qwen/Qwen3.5-4B"
    assert VISION_MODEL_FALLBACK[0] == "Qwen/Qwen3.5-4B"
    assert VisualAnalyzer.MULTIMODAL_MODELS[0] == "Qwen/Qwen3.5-4B"


def test_visual_registry_exposes_three_visual_models():
    visual_models = {
        model.model_key
        for model in get_available_models(CloudModelCapability.VISION)
    }

    assert visual_models == {
        "Qwen/Qwen3.5-4B",
        "PaddlePaddle/PaddleOCR-VL-1.5",
        "deepseek-ai/DeepSeek-OCR",
    }


@pytest.mark.asyncio
async def test_explicit_visual_model_does_not_fallback(monkeypatch, tmp_path):
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"image")
    called = []

    async def fake_call(image_base64, prompt, model, timeout):
        called.append(model)
        return "视觉描述"

    import app.utils.vision
    monkeypatch.setattr(app.utils.vision, "_call_vision_model", fake_call)

    result = await analyze_image(str(image_path), model="PaddlePaddle/PaddleOCR-VL-1.5")

    assert result["model_used"] == "PaddlePaddle/PaddleOCR-VL-1.5"
    assert called == ["PaddlePaddle/PaddleOCR-VL-1.5"]


def test_file_prompt_selects_qwen35():
    assert select_model_for_prompt("分析附件", use_reasoning=False, has_files=True) == "Qwen/Qwen3.5-4B"


def test_removed_glm_visual_model_is_not_registered():
    assert ModelRegistry.get("glm-4.1v-9b") is None


@pytest.mark.asyncio
async def test_visual_analyzer_forwards_user_api_key_token(monkeypatch):
    captured = {}

    async def fake_call_llm(**kwargs):
        captured.update(kwargs)
        return {"choices": [{"message": {"content": '{"slides_analysis": [], "overall_style": {}}'}}]}

    import app.utils
    monkeypatch.setattr(app.utils, "call_llm", fake_call_llm)

    await VisualAnalyzer().analyze_ppt_content(
        title="测试",
        slides_content=[],
        api_key_token="test-token",
    )

    assert captured["api_key_token"] == "test-token"


@pytest.mark.asyncio
async def test_ppt_visual_review_uses_default_visual_model(monkeypatch):
    captured = {}

    async def fake_call_vision_model(**kwargs):
        captured.update(kwargs)
        return "视觉描述"

    import app.utils.vision
    monkeypatch.setattr(app.utils.vision, "_call_vision_model", fake_call_vision_model)

    analyzer = object.__new__(PPTVisualAnalyzer)
    analyzer.api_key_token = "test-token"
    analyzer.user_id = "test-user"

    result = await analyzer._analyze_with_vision(b"image", 1)

    assert result == "视觉描述"
    assert captured["model"] == DEFAULT_VISUAL_MODEL
    assert captured["api_key_token"] == "test-token"
    assert captured["user_id"] == "test-user"


def test_ppt_visual_analyzer_accepts_explicit_model():
    analyzer = object.__new__(PPTVisualAnalyzer)
    analyzer.model = "PaddlePaddle/PaddleOCR-VL-1.5"

    assert analyzer.model == "PaddlePaddle/PaddleOCR-VL-1.5"
