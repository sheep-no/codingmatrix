from pathlib import Path
import json
import os
import logging

logger = logging.getLogger(__name__)

DOMAIN_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "configs" / "domain_templates"

SKIP_COMPLEXITY_LEVELS = {"simple", "small"}

TIME_BUDGET_SECONDS = {
    "medium": 15,
    "large": 20,
    "enterprise": 25,
}

CONFIDENCE_DISPLAY_THRESHOLD = 0.4
CONFIDENCE_DEFAULT_SHOW = 0.7


def _load_dual_models_from_config():
    """从 agent_model_config.json 加载双模型配置（统一配置来源）"""
    config_path = os.path.join(os.path.dirname(__file__), "../../../data/agent_model_config.json")
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # 从 MEDIUM 级别分配中取 architect 和 frontend 作为双模型
            assignments = config.get("assignments", {})
            medium = assignments.get("MEDIUM", {})
            from app.agent.dynamic_model_router import resolve_model_key
            model_a = resolve_model_key(medium.get("backend_model", "deepseek-r1"))
            model_b = resolve_model_key(medium.get("architect_model", "glm-z1-9b"))
            fallback = resolve_model_key(medium.get("frontend_model", "qwen3-8b"))
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
