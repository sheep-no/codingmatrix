from pathlib import Path

import yaml

from app.services.model_config_manager import ModelConfigManager


INITIAL_CONFIG = """\
version: '5.0'
description: 统一模型配置
defaults:
  code: qwen3.5-4b
  architect: qwen3-8b
providers:
  siliconflow:
    name: SiliconFlow
    api_key: ''
    base_url: https://api.siliconflow.cn/v1
    enabled: true
models:
  qwen3-8b:
    name: Qwen/Qwen3-8B
    display_name: Qwen3 8B
    provider: siliconflow
    type: chat
agent:
  roles:
    architect: qwen3-8b
    frontend: deepseek-r1
    backend: nex-n2-pro
    reviewer: glm-z1-9b
    fallback: qwen3-8b
  fallback_chain:
    - qwen3-8b
"""


def test_save_config_preserves_defaults(tmp_path: Path):
    config_path = tmp_path / "unified_model_config.yaml"
    config_path.write_text(INITIAL_CONFIG, encoding="utf-8")

    manager = ModelConfigManager(str(config_path))
    assert manager.update_agent_role("architect", "deepseek-r1") is True

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["defaults"] == {"code": "qwen3.5-4b", "architect": "qwen3-8b"}
