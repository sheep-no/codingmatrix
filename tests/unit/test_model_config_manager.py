"""ModelConfigManager 回归测试（MCM2 同步失败、MCM3 字段注入、MCM4 引用检查）。"""
from app.services.model_config_manager import (
    ModelConfig,
    ModelConfigManager,
    ProviderConfig,
)


def _manager(tmp_path, monkeypatch):
    """构造隔离实例，并阻断 save_config 对全局 Agent runtime 的副作用"""
    manager = ModelConfigManager(config_path=str(tmp_path / "config.yaml"))
    monkeypatch.setattr(manager, "save_config", lambda: True)
    return manager


class TestUpdateIgnoresId:

    def test_update_model_ignores_id(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path, monkeypatch)
        manager._models["a"] = ModelConfig(
            id="a", name="A", display_name="A", provider="siliconflow"
        )

        assert manager.update_model("a", {"id": "b", "name": "B"}) is True

        assert "a" in manager._models
        assert "b" not in manager._models
        assert manager._models["a"].id == "a"
        assert manager._models["a"].name == "B"

    def test_update_provider_ignores_id(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path, monkeypatch)
        manager._providers["p1"] = ProviderConfig(id="p1", name="P1")

        assert manager.update_provider("p1", {"id": "p2", "name": "P2"}) is True

        assert "p1" in manager._providers
        assert "p2" not in manager._providers
        assert manager._providers["p1"].id == "p1"
        assert manager._providers["p1"].name == "P2"


class TestDeleteProviderReferences:

    def test_delete_referenced_provider_rejected(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path, monkeypatch)
        # 默认配置中的模型引用了 siliconflow
        assert any(m.provider == "siliconflow" for m in manager.get_all_models())

        assert manager.delete_provider("siliconflow") is False
        assert manager.get_provider("siliconflow") is not None

    def test_delete_unreferenced_provider_succeeds(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path, monkeypatch)
        manager._providers["p1"] = ProviderConfig(id="p1", name="P1")

        assert manager.delete_provider("p1") is True
        assert manager.get_provider("p1") is None

    def test_delete_unknown_provider_returns_false(self, tmp_path, monkeypatch):
        manager = _manager(tmp_path, monkeypatch)
        assert manager.delete_provider("missing") is False


class TestSyncFailureSurfaced:

    def _real_manager(self, tmp_path, monkeypatch):
        """构造真实 save_config 的实例，仅阻断全局 runtime 刷新副作用"""
        manager = ModelConfigManager(config_path=str(tmp_path / "config.yaml"))
        monkeypatch.setattr(
            ModelConfigManager, "_refresh_runtime_config", staticmethod(lambda: None)
        )
        return manager

    def test_save_config_returns_false_when_agent_sync_fails(self, tmp_path, monkeypatch):
        manager = self._real_manager(tmp_path, monkeypatch)
        monkeypatch.setattr(manager, "_sync_to_agent_config", lambda data: False)

        # 管理面与运行面漂移时必须报告失败，而非静默返回成功
        assert manager.save_config() is False

    def test_save_config_returns_true_on_success(self, tmp_path, monkeypatch):
        manager = self._real_manager(tmp_path, monkeypatch)

        assert manager.save_config() is True
        assert (tmp_path / "config.yaml").exists()
