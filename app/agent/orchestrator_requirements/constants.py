from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)

DOMAIN_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "configs" / "domain_templates"

SKIP_COMPLEXITY_LEVELS = {"simple", "small"}

TIME_BUDGET_SECONDS = {
    "medium": 30,
    "large": 40,
    "enterprise": 45,
}

CONFIDENCE_DISPLAY_THRESHOLD = 0.4
CONFIDENCE_DEFAULT_SHOW = 0.7


def _load_dual_models_from_config():
    """从 Agent 运行时 YAML 配置加载双模型配置。"""
    config_path = os.path.join(os.path.dirname(__file__), "../../../data/agent_model_config.yaml")
    try:
        if os.path.exists(config_path):
            from app.utils.model_config_io import load_model_config
            config = load_model_config(Path(config_path))
            # v3.0: 从 roles 中直接取模型
            roles = config.get("roles", {})
            from app.agent.dynamic_model_router import resolve_model_key
            model_a = resolve_model_key(roles.get("backend", "deepseek-r1"))
            model_b = resolve_model_key(roles.get("architect", "glm-z1-9b"))
            fallback = resolve_model_key(roles.get("frontend", "qwen3-8b"))
            return model_a, model_b, fallback
    except Exception as e:
        logger.warning(f"从配置加载双模型失败，使用默认值: {e}")
    return (
        "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
        "THUDM/GLM-Z1-9B-0414",
        "Qwen/Qwen3-8B",
    )


DUAL_MODEL_A, DUAL_MODEL_B, DUAL_MODEL_FALLBACK = _load_dual_models_from_config()

DEVILS_ADVOCATE_MODEL = "THUDM/GLM-Z1-9B-0414"

MIN_HISTORY_PROJECTS = 50
MIN_HISTORY_WITH_FEATURES = 20
MIN_VECTOR_RESULTS = 5
