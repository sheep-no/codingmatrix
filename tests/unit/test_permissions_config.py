"""permissions/system_config/system_monitor 回归测试。

覆盖 docs/evolution/modules/permissions_config.md 中核实的缺陷：
- SC1：get_user_concurrent_limit 读取路径与默认配置结构不匹配
- SC2：SystemConfigManager.__new__ 单例无锁
- SC5：save_config 无锁
- SM1：get_system_stats 无异常处理
"""
import json
import threading

import pytest

import app.utils.system_monitor as system_monitor
from app.utils.system_config import SystemConfigManager


@pytest.fixture
def manager():
    m = SystemConfigManager()
    original_config = m._config
    original_file = m._config_file
    yield m
    m._config = original_config
    m._config_file = original_file


class TestConcurrentLimitRead:

    def test_reads_role_defaults_from_default_config_structure(self, manager):
        """默认配置把 role_defaults 放在顶层，读取路径必须能命中"""
        manager._config = manager._get_default_config()

        assert manager.get_user_concurrent_limit("u1", "free") == 1
        assert manager.get_user_concurrent_limit("u1", "basic") == 2
        assert manager.get_user_concurrent_limit("u1", "premium") == 5
        assert manager.get_user_concurrent_limit("u1", "superadmin") == 50

    def test_reads_default_tiers_from_deployed_config_structure(self, manager):
        """既有部署文件把 default_tiers 放在 system_config 内，需保持兼容"""
        manager._config = {
            "system_config": {
                "user_concurrent_limits": {
                    "default_tiers": {"free": 1, "premium": 5},
                    "user_overrides": {},
                }
            }
        }

        assert manager.get_user_concurrent_limit("u1", "premium") == 5

    def test_user_override_wins_over_role_default(self, manager):
        manager._config = manager._get_default_config()
        manager._config.setdefault("system_config", {}).setdefault(
            "user_concurrent_limits", {}
        ).setdefault("user_overrides", {})["u9"] = {"limit": 42, "tier": "custom"}

        assert manager.get_user_concurrent_limit("u9", "free") == 42
        assert manager.get_user_concurrent_limit("u1", "free") == 1

    def test_unknown_role_falls_back_to_free(self, manager):
        manager._config = manager._get_default_config()
        assert manager.get_user_concurrent_limit("u1", "nonexistent") == 1


class TestSystemConfigManager:

    def test_singleton_identity(self):
        assert SystemConfigManager() is SystemConfigManager()

    def test_save_config_is_serialized(self, manager, tmp_path):
        """并发保存后文件仍是合法 JSON 且包含最新写入"""
        manager._config = manager._get_default_config()
        manager._config_file = tmp_path / "system_config.json"

        errors = []

        def _save():
            try:
                manager.save_config()
            except Exception as exc:  # pragma: no cover - 仅记录异常
                errors.append(exc)

        threads = [threading.Thread(target=_save) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        saved = json.loads(manager._config_file.read_text())
        assert "last_updated" in saved["system_config"]


class TestSystemMonitorDegrade:

    def test_returns_degraded_stats_when_psutil_raises(self, monkeypatch):
        class _BrokenPsutil:
            @staticmethod
            def cpu_percent(**kwargs):
                raise RuntimeError("boom")

        monkeypatch.setattr(system_monitor, "_HAS_PSUTIL", True, raising=False)
        monkeypatch.setattr(system_monitor, "psutil", _BrokenPsutil)

        stats = system_monitor.get_system_stats()

        assert stats["error"]
        assert stats["cpu"]["total_percent"] == 0.0
        assert stats["memory"]["percent"] == 0.0
        assert stats["network"]["bytes_sent"] == 0

    def test_returns_degraded_stats_when_psutil_missing(self, monkeypatch):
        monkeypatch.setattr(system_monitor, "_HAS_PSUTIL", False, raising=False)

        stats = system_monitor.get_system_stats()

        assert stats["error"] == "psutil 不可用"
        assert stats["cpu"]["total_percent"] == 0.0

    def test_normal_path_has_no_error_key(self):
        stats = system_monitor.get_system_stats()

        assert "error" not in stats
        assert "timestamp" in stats
