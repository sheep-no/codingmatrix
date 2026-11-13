"""ModelConfigManager 管理操作与单例分支补测。"""

from unittest.mock import MagicMock, patch

import pytest

import app.services.model_config_manager as mcm
from app.services.model_config_manager import (
    ModelConfig,
    ModelConfigManager,
    ProviderConfig,
)


def _manager(tmp_path, monkeypatch, save_ok=True):
    manager = ModelConfigManager(config_path=str(tmp_path / "config.yaml"))
    monkeypatch.setattr(manager, "save_config", lambda: save_ok)
    return manager


class TestBackupCorruptConfig:
    def test_returns_early_when_file_missing(self, tmp_path):
        manager = ModelConfigManager(config_path=str(tmp_path / "config.yaml"))
        manager.config_path = tmp_path / "missing.yaml"

        manager._backup_corrupt_config()

        assert not (tmp_path / "missing.yaml").exists()

    def test_backup_failure_is_logged(self, tmp_path, monkeypatch):
        manager = ModelConfigManager(config_path=str(tmp_path / "config.yaml"))
        manager.config_path = tmp_path / "config.yaml"
        manager.config_path.write_text("x", encoding="utf-8")

        def boom(_target):
            raise OSError("read-only")

        monkeypatch.setattr(type(manager.config_path), "replace", boom)
        manager._backup_corrupt_config()

        assert manager.config_path.exists()


class TestSaveConfigFailurePaths:
    def test_save_config_returns_false_on_io_error(self, tmp_path, monkeypatch):
        manager = ModelConfigManager(config_path=str(tmp_path / "config.yaml"))
        monkeypatch.setattr(
            mcm, "save_model_config", MagicMock(side_effect=OSError("disk full"))
        )

        assert manager.save_config() is False

    def test_refresh_runtime_config_swallows_import_errors(self):
        with patch(
            "app.agent.dynamic_model_router.invalidate_model_mapping_cache",
            side_effect=RuntimeError("router down"),
        ):
            ModelConfigManager._refresh_runtime_config()


class TestSyncToAgentConfig:
    def test_existing_agent_config_fields_are_preserved(self, tmp_path):
        target = tmp_path / "agent_model_config.yaml"
        target.write_text(
            "error_type_models:\n  timeout: qwen3-8b\nsettings:\n  retries: 2\n",
            encoding="utf-8",
        )
        manager = ModelConfigManager(config_path=str(tmp_path / "config.yaml"))

        ok = manager._sync_to_agent_config(
            {
                "models": {"m1": {"name": "M1"}},
                "agent": {"roles": {"architect": "m1"}, "fallback_chain": ["m1"]},
            }
        )

        assert ok is True
        from app.utils.model_config_io import load_model_config

        synced = load_model_config(target)
        assert synced["error_type_models"] == {"timeout": "qwen3-8b"}
        assert synced["settings"] == {"retries": 2}
        assert synced["models"]["m1"]["max_tokens"] == 8192

    def test_sync_failure_is_reported(self, tmp_path, monkeypatch):
        manager = ModelConfigManager(config_path=str(tmp_path / "config.yaml"))
        monkeypatch.setattr(
            mcm, "save_model_config", MagicMock(side_effect=OSError("nope"))
        )

        assert manager._sync_to_agent_config({"models": {}}) is False


class TestModelCrud:
    def test_get_and_list_models(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path, monkeypatch)
        manager._models = {
            "b": ModelConfig(id="b", name="B", display_name="B", provider="p", enabled=False),
            "a": ModelConfig(id="a", name="A", display_name="A", provider="p"),
        }

        assert manager.get_model("a").name == "A"
        assert manager.get_model("missing") is None
        assert [m.id for m in manager.get_all_models()] == ["a", "b"]
        assert [m.id for m in manager.get_all_models(enabled_only=True)] == ["a"]

    def test_add_update_delete_toggle_model(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path, monkeypatch)
        model = ModelConfig(id="m", name="M", display_name="M", provider="p")

        assert manager.add_model(model) is True
        assert "m" in manager._models

        assert manager.update_model("missing", {"name": "X"}) is False
        assert manager.update_model("m", {"name": "M2", "unknown": 1}) is True
        assert manager._models["m"].name == "M2"

        assert manager.toggle_model("m") is True
        assert manager._models["m"].enabled is False
        assert manager.toggle_model("missing") is False

        assert manager.delete_model("m") is True
        assert manager.delete_model("m") is False


class TestProviderCrud:
    def test_get_and_list_providers(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path, monkeypatch)
        manager._providers = {"p": ProviderConfig(id="p", name="P")}

        assert manager.get_provider("p").name == "P"
        assert manager.get_provider("missing") is None
        assert [p.id for p in manager.get_all_providers()] == ["p"]

    def test_add_and_update_provider(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path, monkeypatch)

        assert manager.add_provider(ProviderConfig(id="p", name="P")) is True
        assert manager.update_provider("missing", {"name": "X"}) is False
        assert manager.update_provider("p", {"name": "P2"}) is True
        assert manager._providers["p"].name == "P2"


class TestAgentConfig:
    def test_get_agent_config_returns_instance(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path, monkeypatch)
        assert manager.get_agent_config() is manager._agent_config

    def test_update_agent_role_accepts_known_roles(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path, monkeypatch)

        assert manager.update_agent_role("architect", "m1") is True
        assert manager._agent_config.roles["architect"] == "m1"

    def test_update_agent_role_rejects_unknown_role(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path, monkeypatch)

        assert manager.update_agent_role("unknown", "m1") is False

    def test_update_fallback_chain(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path, monkeypatch)

        assert manager.update_fallback_chain(["m1", "m2"]) is True
        assert manager._agent_config.fallback_chain == ["m1", "m2"]


class TestModelQueries:
    def test_type_and_feature_queries(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path, monkeypatch)
        manager._models = {
            "chat": ModelConfig(id="chat", name="Chat", display_name="C", provider="p"),
            "embed": ModelConfig(
                id="embed", name="Embed", display_name="E", provider="p", model_type="embedding"
            ),
            "vision": ModelConfig(
                id="vision", name="Vision", display_name="V", provider="p", model_type="vision"
            ),
            "image": ModelConfig(
                id="image", name="Image", display_name="I", provider="p", model_type="image"
            ),
            "reasoner": ModelConfig(
                id="reasoner", name="R", display_name="R", provider="p", is_reasoning=True
            ),
            "disabled": ModelConfig(
                id="disabled",
                name="D",
                display_name="D",
                provider="p",
                model_type="embedding",
                enabled=False,
            ),
        }

        assert {m.id for m in manager.get_chat_models()} == {"chat", "reasoner"}
        assert [m.id for m in manager.get_embedding_models()] == ["embed"]
        assert {m.id for m in manager.get_vision_models()} == {"vision", "image"}
        assert [m.id for m in manager.get_reasoning_models()] == ["reasoner"]
        assert {m.id for m in manager.get_models_by_type("chat")} == {"chat", "reasoner"}

    def test_empty_collections_return_empty_lists(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path, monkeypatch)
        manager._models = {}

        assert manager.get_embedding_models() == []
        assert manager.get_vision_models() == []
        assert manager.get_reasoning_models() == []

    def test_get_model_by_name(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path, monkeypatch)
        manager._models = {
            "a": ModelConfig(id="a", name="API-A", display_name="A", provider="p"),
        }

        assert manager.get_model_by_name("API-A").id == "a"
        assert manager.get_model_by_name("missing") is None


class TestSingleton:
    def test_get_manager_creates_once(self, monkeypatch):
        created = []

        class FakeManager:
            def __init__(self):
                created.append(self)

        monkeypatch.setattr(mcm, "_manager", None)
        monkeypatch.setattr(mcm, "ModelConfigManager", FakeManager)

        first = mcm.get_model_config_manager()
        second = mcm.get_model_config_manager()

        assert first is second
        assert len(created) == 1

    def test_reload_replaces_manager(self, monkeypatch):
        created = []

        class FakeManager:
            @staticmethod
            def _refresh_runtime_config():
                created.append("refresh")

            def __init__(self):
                created.append("init")

        monkeypatch.setattr(mcm, "_manager", object())
        monkeypatch.setattr(mcm, "ModelConfigManager", FakeManager)

        manager = mcm.reload_model_config()

        assert isinstance(manager, FakeManager)
        assert created == ["init", "refresh"]

    def test_get_manager_skips_creation_when_already_set(self, monkeypatch):
        existing = object()
        monkeypatch.setattr(mcm, "_manager", existing)

        assert mcm.get_model_config_manager() is existing

    def test_get_manager_rechecks_after_acquiring_lock(self, monkeypatch):
        created = []

        class FakeManager:
            def __init__(self):
                created.append(self)

        winner = FakeManager()

        class RaceLock:
            def __enter__(self):
                # 模拟另一个线程在两次判空之间完成初始化
                monkeypatch.setattr(mcm, "_manager", winner)
                return self

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(mcm, "_manager", None)
        monkeypatch.setattr(mcm, "_lock", RaceLock())
        monkeypatch.setattr(mcm, "ModelConfigManager", FakeManager)

        assert mcm.get_model_config_manager() is winner
        assert created == [winner]
