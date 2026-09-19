from pathlib import Path

import pytest
import yaml

from app.utils.model_config_io import load_model_config, save_model_config


def test_save_and_load_preserves_nested_unicode_config(tmp_path: Path):
    path = tmp_path / "nested" / "model.yaml"
    config = {
        "providers": {
            "本地模型": {
                "base_url": "http://127.0.0.1:8000/v1",
                "models": ["模型-A", "model-b"],
            }
        },
        "enabled": True,
    }

    save_model_config(path, config)

    assert load_model_config(path) == config
    assert "本地模型" in path.read_text(encoding="utf-8")


def test_load_empty_yaml_returns_empty_dict(tmp_path: Path):
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")

    assert load_model_config(path) == {}


def test_load_invalid_yaml_raises_yaml_error(tmp_path: Path):
    path = tmp_path / "invalid.yaml"
    path.write_text("providers: [", encoding="utf-8")

    with pytest.raises(yaml.YAMLError):
        load_model_config(path)


def test_save_is_atomic(tmp_path: Path):
    """写入通过临时文件原子替换，不留半截文件与 .tmp 残留"""
    path = tmp_path / "model.yaml"

    save_model_config(path, {"version": "1.0", "models": {"a": {"name": "b"}}})
    save_model_config(path, {"version": "1.0", "models": {"a": {"name": "c"}}})

    assert load_model_config(path)["models"]["a"]["name"] == "c"
    assert list(tmp_path.glob("*.tmp")) == []


def test_corrupt_config_is_backed_up_not_overwritten(tmp_path: Path):
    """损坏配置在回退默认前被备份，历史内容不会因后续保存而永久丢失"""
    from app.services.model_config_manager import ModelConfigManager

    path = tmp_path / "unified_model_config.yaml"
    path.write_text("providers: [", encoding="utf-8")

    ModelConfigManager(config_path=str(path))

    assert not path.exists()
    backups = list(tmp_path.glob("unified_model_config.yaml.corrupt.*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "providers: ["
