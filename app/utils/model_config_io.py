"""模型配置 YAML 读写工具。"""

import os
from pathlib import Path
from typing import Any, Dict

import yaml


def load_model_config(path: Path) -> Dict[str, Any]:
    """读取模型配置 YAML，并将空文件规范化为空字典。"""
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def save_model_config(path: Path, config: Dict[str, Any]) -> None:
    """以稳定、可读的 YAML 格式保存模型配置。

    先写同目录临时文件再原子替换，避免写入中途崩溃留下半截 YAML——
    半截文件会被读取方解析失败并按默认配置回退，随后被整份覆盖。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(
            config,
            file,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    os.replace(tmp_path, path)
