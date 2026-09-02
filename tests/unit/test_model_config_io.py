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
