"""视觉任务应统一使用 Qwen3.5 作为主模型。"""

from app.agent.models import ModelRegistry, ModelRouter, ModelCapability, TaskType
from app.api.v1.Aicode import select_model_for_prompt
from app.utils.vision import IMAGE_DESC_MODEL, VISION_MODEL, VISION_MODEL_FALLBACK
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


def test_file_prompt_selects_qwen35():
    assert select_model_for_prompt("分析附件", use_reasoning=False, has_files=True) == "Qwen/Qwen3.5-4B"


def test_removed_glm_visual_model_is_not_registered():
    assert ModelRegistry.get("glm-4.1v-9b") is None
