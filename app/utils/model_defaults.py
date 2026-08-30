"""统一读取模型默认值。"""

from pathlib import Path
from typing import Dict

import yaml

from app.utils.model_config_io import load_model_config


_CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "unified_model_config.yaml"

# YAML 不可用时的最小安全兜底，正常运行时以 unified_model_config.yaml 为准。
_FALLBACK_DEFAULTS = {
    "code": "Qwen/Qwen2.5-7B-Instruct",
    "reasoning": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
    "architect": "THUDM/GLM-Z1-9B-0414",
    "fast": "Qwen/Qwen3-8B",
    "visual": "Qwen/Qwen3.5-4B",
    "ocr": "deepseek-ai/DeepSeek-OCR",
    "embedding": "BAAI/bge-m3",
    "ppt": "Qwen/Qwen3.5-4B",
}


def _load_defaults() -> Dict[str, str]:
    try:
        config = load_model_config(_CONFIG_PATH)
        models = config.get("models", {})
        configured = config.get("defaults", {})
        defaults = {}
        for purpose, fallback in _FALLBACK_DEFAULTS.items():
            model_id = configured.get(purpose, fallback)
            model = models.get(model_id, {})
            defaults[purpose] = model.get("name", model_id)
        return defaults
    except (OSError, TypeError, AttributeError, ValueError, yaml.YAMLError):
        return _FALLBACK_DEFAULTS.copy()


MODEL_DEFAULTS = _load_defaults()


def get_default_model(purpose: str) -> str:
    """按用途返回统一配置中的模型名称。"""
    return MODEL_DEFAULTS.get(purpose, _FALLBACK_DEFAULTS["fast"])
