"""锁定 `MODEL_REGISTRY` 与 unified_model_config.yaml 的 siliconflow 模型一致。

回归背景：注册表曾出现 4 个重复键（字面量 22 条、唯一 18 个，后写静默覆盖前写），
`bge-reranker` 键名与配置不一致，另有 4 处 `max_tokens`/`max_context` 与配置漂移。
本测试以配置为准，防止两套模型表再次分叉。
"""

import ast
from pathlib import Path

from app.utils.aicloud import model_registry as model_registry_module
from app.utils.aicloud.model_registry import MODEL_REGISTRY
from app.utils.model_config_io import load_model_config


_CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "unified_model_config.yaml"


def _siliconflow_models() -> dict:
    config = load_model_config(_CONFIG_PATH)
    return {
        key: value
        for key, value in config.get("models", {}).items()
        if value.get("provider") == "siliconflow"
    }


def test_registry_keys_match_configured_siliconflow_models():
    configured = _siliconflow_models()
    assert set(MODEL_REGISTRY) == set(configured)
    assert len(MODEL_REGISTRY) == 18


def test_registry_entries_match_config_values():
    configured = _siliconflow_models()
    for key, entry in MODEL_REGISTRY.items():
        expected = configured[key]
        assert entry.id == key, f"{key}: id 与注册表键不一致"
        assert entry.model_key == expected["name"], f"{key}: model_key 与配置 name 不一致"
        assert entry.max_tokens == expected["max_output"], f"{key}: max_tokens 与配置 max_output 不一致"
        assert entry.max_context == expected["context_length"], f"{key}: max_context 与配置 context_length 不一致"


def test_registry_has_no_duplicate_keys():
    """注册表字面量不得重复声明同一键（重复键会被后写静默覆盖）。"""
    source = Path(model_registry_module.__file__).read_text(encoding="utf-8")
    literal_keys = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "MODEL_REGISTRY":
            literal_keys = [k.value for k in node.value.keys]
    assert len(literal_keys) == len(set(literal_keys)) == len(MODEL_REGISTRY)
