"""app/utils/system_config.py 的配置读写、并发委托与 DB 查询分支。"""

import json
from pathlib import Path

import pytest

from app.utils import system_config as system_config_module
from app.utils.system_config import SystemConfigManager, system_config_manager


@pytest.fixture
def manager(monkeypatch):
    """隔离全局单例状态，避免用例之间互相污染配置内容。"""
    original_config = dict(system_config_manager._config)
    monkeypatch.setattr(system_config_manager, "save_config", lambda: None)
    yield system_config_manager
    system_config_manager._config = original_config


class TestSingleton:
    def test_new_returns_same_instance(self, monkeypatch):
        monkeypatch.setattr(SystemConfigManager, "load_config", lambda self: None)

        class _StubConcurrentManager:
            def __init__(self):
                pass

        monkeypatch.setattr(
            "app.utils.dynamic_concurrent.ConcurrentLimitManager",
            _StubConcurrentManager,
        )

        original = SystemConfigManager._instance
        try:
            SystemConfigManager._instance = None
            first = SystemConfigManager()
            second = SystemConfigManager()
            assert first is second
        finally:
            SystemConfigManager._instance = original

    def test_double_checked_lock_returns_instance_created_by_another_thread(self):
        """并发下另一线程已建好实例时，内层检查应直接返回它。"""
        sentinel = object()
        original_instance = SystemConfigManager._instance
        original_lock = SystemConfigManager._instance_lock

        class _RacingLock:
            def __enter__(self):
                SystemConfigManager._instance = sentinel
                return self

            def __exit__(self, *args):
                return False

        try:
            SystemConfigManager._instance = None
            SystemConfigManager._instance_lock = _RacingLock()
            assert SystemConfigManager() is sentinel
        finally:
            SystemConfigManager._instance = original_instance
            SystemConfigManager._instance_lock = original_lock


class TestLoadConfig:
    def test_reads_existing_file(self, monkeypatch, tmp_path):
        config_file = tmp_path / "system_config.json"
        config_file.write_text(json.dumps({"system_config": {"version": "9"}}), encoding="utf-8")
        monkeypatch.setattr(SystemConfigManager, "_config_file", config_file)

        manager = object.__new__(SystemConfigManager)
        manager.load_config()

        assert manager._config == {"system_config": {"version": "9"}}

    def test_missing_file_falls_back_to_defaults_and_saves(self, monkeypatch, tmp_path):
        monkeypatch.setattr(SystemConfigManager, "_config_file", tmp_path / "missing.json")
        saved = {}
        monkeypatch.setattr(SystemConfigManager, "save_config", lambda self: saved.setdefault("called", True))

        manager = object.__new__(SystemConfigManager)
        manager.load_config()

        assert manager._config["session_management"]["max_active_sessions"] == 100
        assert saved["called"] is True

    def test_invalid_json_falls_back_without_saving(self, monkeypatch, tmp_path):
        config_file = tmp_path / "broken.json"
        config_file.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(SystemConfigManager, "_config_file", config_file)
        calls = []
        monkeypatch.setattr(SystemConfigManager, "save_config", lambda self: calls.append(1))

        manager = object.__new__(SystemConfigManager)
        manager.load_config()

        assert manager._config["system_config"]["version"] == "1.0"
        assert calls == []


class TestSaveConfig:
    def test_writes_timestamp_and_content(self, monkeypatch, tmp_path):
        config_file = tmp_path / "nested" / "system_config.json"
        monkeypatch.setattr(SystemConfigManager, "_config_file", config_file)

        manager = object.__new__(SystemConfigManager)
        manager._config = {"system_config": {"version": "1.0"}}
        manager.save_config()

        stored = json.loads(config_file.read_text(encoding="utf-8"))
        assert stored["system_config"]["version"] == "1.0"
        assert "last_updated" in stored["system_config"]

    def test_write_failure_is_swallowed(self, monkeypatch, tmp_path):
        # 把配置文件指向目录，open 时必然失败
        monkeypatch.setattr(SystemConfigManager, "_config_file", tmp_path)

        manager = object.__new__(SystemConfigManager)
        manager._config = {"system_config": {}}

        manager.save_config()


class TestConcurrentLimits:
    def test_user_override_takes_precedence(self, manager):
        manager._config = {
            "system_config": {
                "user_concurrent_limits": {"user_overrides": {"42": {"limit": 7}}}
            },
            "user_concurrent_limits": {"role_defaults": {"premium": 5}},
        }

        assert manager.get_user_concurrent_limit("42", "premium") == 7

    @pytest.mark.parametrize(
        "config",
        [
            {"user_concurrent_limits": {"role_defaults": {"premium": 5}}},
            {"system_config": {"user_concurrent_limits": {"role_defaults": {"premium": 5}}}},
            {"system_config": {"user_concurrent_limits": {"default_tiers": {"premium": 5}}}},
            {"user_concurrent_limits": {"default_tiers": {"premium": 5}}},
        ],
    )
    def test_role_defaults_resolve_from_multiple_layouts(self, manager, config):
        manager._config = config
        assert manager.get_user_concurrent_limit("42", "premium") == 5

    def test_unknown_role_falls_back_to_free_default(self, manager):
        manager._config = {"user_concurrent_limits": {"role_defaults": {"free": 2}}}
        assert manager.get_user_concurrent_limit("42", "ghost") == 2

    def test_completely_unknown_role_defaults_to_one(self, manager):
        manager._config = {}
        assert manager.get_user_concurrent_limit("42", "ghost") == 1

    def test_override_without_limit_field_defaults_to_one(self, manager):
        manager._config = {
            "system_config": {"user_concurrent_limits": {"user_overrides": {"42": {}}}}
        }
        assert manager.get_user_concurrent_limit("42") == 1


class TestConcurrentDelegation:
    class _StubManager:
        def __init__(self):
            self.calls = []

        def can_create_session(self, role):
            self.calls.append(("can_create_session", role))
            return role != "blocked"

        async def update_limit(self, role, limit, changed_by, reason):
            self.calls.append(("update_limit", role, limit, changed_by, reason))
            return {"role": role, "limit": limit}

        def get_limit(self, role):
            self.calls.append(("get_limit", role))
            return 11

        def get_change_history(self, limit):
            self.calls.append(("get_change_history", limit))
            return [{"limit": limit}]

    @pytest.mark.asyncio
    async def test_delegates_to_concurrent_manager(self, manager, monkeypatch):
        stub = self._StubManager()
        monkeypatch.setattr(manager, "concurrent_mgr", stub)

        assert manager.can_create_new_session("42", user_role="free") is True
        assert manager.can_create_new_session("42", user_role="blocked") is False
        assert await manager.update_concurrent_limit("free", 3, "admin", "test") == {
            "role": "free",
            "limit": 3,
        }
        assert manager.get_concurrent_limit("free") == 11
        assert manager.get_limit_change_history(20) == [{"limit": 20}]
        assert stub.calls == [
            ("can_create_session", "free"),
            ("can_create_session", "blocked"),
            ("update_limit", "free", 3, "admin", "test"),
            ("get_limit", "free"),
            ("get_change_history", 20),
        ]


class TestUserOverride:
    def test_update_writes_nested_override(self, manager):
        manager._config = {}

        manager.update_user_override("42", 8, tier="vip")

        overrides = manager._config["system_config"]["user_concurrent_limits"]["user_overrides"]
        assert overrides["42"] == {"limit": 8, "tier": "vip"}

    def test_remove_deletes_existing_override(self, manager):
        manager._config = {
            "system_config": {
                "user_concurrent_limits": {"user_overrides": {"42": {"limit": 8}}}
            }
        }

        manager.remove_user_override("42")

        assert manager._config["system_config"]["user_concurrent_limits"]["user_overrides"] == {}

    def test_remove_missing_override_is_noop(self, manager):
        manager._config = {"system_config": {"user_concurrent_limits": {"user_overrides": {}}}}
        manager.remove_user_override("missing")
        assert manager._config["system_config"]["user_concurrent_limits"]["user_overrides"] == {}


class TestConfigValues:
    def test_get_nested_value(self, manager):
        manager._config = {"a": {"b": {"c": 1}}}
        assert manager.get_config_value("a.b.c") == 1

    @pytest.mark.parametrize("path", ["a.missing", "a.b.c.d", "x.y"])
    def test_missing_path_returns_default(self, manager, path):
        manager._config = {"a": {"b": {"c": 1}}}
        assert manager.get_config_value(path, default="fallback") == "fallback"

    def test_type_error_returns_default(self, manager):
        manager._config = {"a": {"b": 1}}
        assert manager.get_config_value("a.b.c", default=None) is None

    def test_set_nested_value_creates_intermediate_dicts(self, manager):
        manager._config = {}

        manager.set_config_value("a.b.c", 5)

        assert manager._config == {"a": {"b": {"c": 5}}}


class TestActiveSessions:
    @pytest.mark.asyncio
    async def test_returns_serialized_running_sessions(self, manager, monkeypatch):
        class _Session:
            def __init__(self, sid):
                self.sid = sid

            def to_dict(self):
                return {"id": self.sid}

        class _Scalars:
            def all(self):
                return [_Session(1), _Session(2)]

        class _Result:
            def scalars(self):
                return _Scalars()

        class _FakeSessionCtx:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def execute(self, stmt):
                return _Result()

        monkeypatch.setattr(
            "app.db.database.async_session", lambda: _FakeSessionCtx()
        )

        assert await manager.get_active_sessions_for_user("42") == [{"id": 1}, {"id": 2}]

    @pytest.mark.asyncio
    async def test_database_error_returns_empty_list(self, manager, monkeypatch):
        class _BrokenCtx:
            async def __aenter__(self):
                raise RuntimeError("db down")

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr("app.db.database.async_session", lambda: _BrokenCtx())

        assert await manager.get_active_sessions_for_user("42") == []

    @pytest.mark.asyncio
    async def test_non_numeric_user_id_returns_empty_list(self, manager):
        assert await manager.get_active_sessions_for_user("not-a-number") == []
