"""Branch coverage for app/services/resource_config.py."""

import asyncio
import importlib
import time

import pytest

rc_module = importlib.import_module("app.services.resource_config")


@pytest.fixture()
def service(monkeypatch):
    monkeypatch.setattr(rc_module.ResourceConfigService, "_instance", None)
    return rc_module.ResourceConfigService()


class _Column:
    def __eq__(self, other):
        return self

    def in_(self, other):
        return self


class _Config:
    DEFAULT_CONFIGS = {
        "existing": {"value": "1", "description": "d1"},
        "seeded": {"value": "2", "description": "d2"},
    }
    key = _Column()

    def __init__(self, key, value, description="", updated_by=None):
        self.key = key
        self.value = value
        self.description = description
        self.updated_by = updated_by


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _Result:
    def __init__(self, rows, scalar=None):
        self._rows = rows
        self._scalar = scalar

    def scalars(self):
        return _Scalars(self._rows)

    def scalar_one_or_none(self):
        return self._scalar


class _Session:
    def __init__(self, rows=(), scalar=None, fail_commit=False):
        self.rows = list(rows)
        self.scalar = scalar
        self.fail_commit = fail_commit
        self.added = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, _statement):
        return _Result(self.rows, self.scalar)

    def add(self, instance):
        self.added.append(instance)

    async def commit(self):
        if self.fail_commit:
            raise RuntimeError("commit failed")
        self.commits += 1


@pytest.fixture(autouse=True)
def _patch_model(monkeypatch):
    monkeypatch.setattr(rc_module, "ServerConfig", _Config)
    # execute() is faked, so keep SQLAlchemy from coercing the fake model class.
    stub = type("Stmt", (), {"where": lambda self, *_a: self})
    monkeypatch.setattr(rc_module, "select", lambda *_a, **_k: stub())
    yield


class TestSingleton:
    def test_second_init_keeps_state(self, service):
        service._config_cache["k"] = "v"
        again = rc_module.ResourceConfigService()
        assert again is service
        assert again._config_cache == {"k": "v"}


class TestEnsureCacheLoaded:
    async def test_fresh_cache_skips_db(self, service):
        service._cache_loaded = True
        service._cache_loaded_at = time.monotonic()
        session = _Session()

        await service._ensure_cache_loaded(session)

        assert session.commits == 0

    async def test_loads_rows_and_seeds_missing_defaults(self, service):
        session = _Session(rows=[_Config("existing", "old")])

        await service._ensure_cache_loaded(session)

        assert service._config_cache == {"existing": "old", "seeded": "2"}
        assert [c.key for c in session.added] == ["seeded"]
        assert service._cache_loaded is True
        assert service._cache_loaded_at > 0

    async def test_double_check_skips_reload_when_cache_became_fresh(self, service, monkeypatch):
        calls = {"n": 0}

        class RacingLock:
            async def __aenter__(self):
                # Another coroutine finished loading while we waited for the lock.
                service._cache_loaded = True
                service._cache_loaded_at = time.monotonic()
                return self

            async def __aexit__(self, *exc):
                return False

        monkeypatch.setattr(service, "_cache_lock", RacingLock())
        session = _Session()
        monkeypatch.setattr(
            session, "execute", lambda *_a: calls.__setitem__("n", calls["n"] + 1)
        )

        await service._ensure_cache_loaded(session)

        assert calls["n"] == 0


class TestGetConfig:
    async def test_returns_cached_value_without_db(self, service, monkeypatch):
        service._cache_loaded = True
        service._cache_loaded_at = time.monotonic()
        service._config_cache["k"] = "v"

        def _no_session():
            raise AssertionError("should not open a session")

        monkeypatch.setattr(rc_module, "async_session", _no_session)

        assert await service.get_config("k") == "v"

    async def test_falls_back_to_default(self, service, monkeypatch):
        session = _Session(rows=[])

        async def ensure(_db):
            service._config_cache = {}
            service._cache_loaded = True
            service._cache_loaded_at = time.monotonic()

        monkeypatch.setattr(service, "_ensure_cache_loaded", ensure)
        monkeypatch.setattr(rc_module, "async_session", lambda: session)

        assert await service.get_config("missing", "fallback") == "fallback"

    async def test_returns_none_without_default(self, service, monkeypatch):
        session = _Session(rows=[])

        async def ensure(_db):
            service._cache_loaded = True
            service._cache_loaded_at = time.monotonic()

        monkeypatch.setattr(service, "_ensure_cache_loaded", ensure)
        monkeypatch.setattr(rc_module, "async_session", lambda: session)

        assert await service.get_config("missing") is None


class TestSetConfig:
    async def test_updates_existing_row(self, service, monkeypatch):
        row = _Config("k", "old")
        session = _Session(rows=[row], scalar=row)

        async def ensure(_db):
            service._cache_loaded = True
            service._cache_loaded_at = time.monotonic()

        monkeypatch.setattr(service, "_ensure_cache_loaded", ensure)
        monkeypatch.setattr(rc_module, "async_session", lambda: session)

        assert await service.set_config("k", "new", user_id=7) is True

        assert row.value == "new"
        assert row.updated_by == 7
        assert service._config_cache["k"] == "new"
        assert session.added == []

    async def test_existing_row_without_user_keeps_updated_by(self, service, monkeypatch):
        row = _Config("k", "old")
        row.updated_by = 3
        session = _Session(rows=[row], scalar=row)

        async def ensure(_db):
            service._cache_loaded = True
            service._cache_loaded_at = time.monotonic()

        monkeypatch.setattr(service, "_ensure_cache_loaded", ensure)
        monkeypatch.setattr(rc_module, "async_session", lambda: session)

        assert await service.set_config("k", "new") is True
        assert row.updated_by == 3

    async def test_creates_missing_row(self, service, monkeypatch):
        session = _Session(rows=[], scalar=None)

        async def ensure(_db):
            service._cache_loaded = True
            service._cache_loaded_at = time.monotonic()

        monkeypatch.setattr(service, "_ensure_cache_loaded", ensure)
        monkeypatch.setattr(rc_module, "async_session", lambda: session)

        assert await service.set_config("new-key", "v", description="desc") is True

        added = session.added[0]
        assert added.key == "new-key"
        assert added.description == "desc"
        assert added.updated_by is None
        assert service._config_cache["new-key"] == "v"


class TestGetAllConfigs:
    async def test_returns_copy_of_cache(self, service, monkeypatch):
        session = _Session()

        async def ensure(_db):
            service._config_cache = {"a": "1", "b": "2"}
            service._cache_loaded = True
            service._cache_loaded_at = time.monotonic()

        monkeypatch.setattr(service, "_ensure_cache_loaded", ensure)
        monkeypatch.setattr(rc_module, "async_session", lambda: session)

        result = await service.get_all_configs()

        assert result == {"a": "1", "b": "2"}
        result["c"] = "3"
        assert "c" not in service._config_cache


class TestBatchUpdate:
    async def test_creates_with_default_description(self, service, monkeypatch):
        session = _Session(rows=[])
        monkeypatch.setattr(rc_module, "async_session", lambda: session)

        assert await service.batch_update_configs({"existing": "x"}, user_id=9) is True

        added = session.added[0]
        assert added.key == "existing"
        assert added.description == "d1"
        assert added.updated_by == 9

    async def test_unknown_key_gets_empty_description(self, service, monkeypatch):
        session = _Session(rows=[])
        monkeypatch.setattr(rc_module, "async_session", lambda: session)

        await service.batch_update_configs({"brand-new": "x"})

        assert session.added[0].description == ""

    async def test_existing_row_without_user_keeps_updated_by(self, service, monkeypatch):
        row = _Config("a", "1")
        row.updated_by = 42
        session = _Session(rows=[row])
        monkeypatch.setattr(rc_module, "async_session", lambda: session)

        await service.batch_update_configs({"a": "2"})

        assert row.value == "2"
        assert row.updated_by == 42

    async def test_existing_row_with_user_sets_updated_by(self, service, monkeypatch):
        row = _Config("a", "1")
        session = _Session(rows=[row])
        monkeypatch.setattr(rc_module, "async_session", lambda: session)

        await service.batch_update_configs({"a": "2"}, user_id=11)

        assert row.updated_by == 11


class TestServerStats:
    async def test_empty_config_falls_back_through_get_config(self, service, monkeypatch):
        import psutil

        monkeypatch.setattr(
            psutil,
            "virtual_memory",
            lambda: type(
                "M", (), {"total": 10, "used": 4, "percent": 40.0, "available": 6}
            )(),
        )
        monkeypatch.setattr(
            psutil,
            "disk_usage",
            lambda _p: type("D", (), {"total": 20, "used": 5, "percent": 25.0})(),
        )
        monkeypatch.setattr(psutil, "cpu_percent", lambda _i: 12.0)

        async def fake_count():
            return 2

        async def fake_config(_key, default=None):
            return "5"

        monkeypatch.setattr(service, "_get_docker_container_count", fake_count)
        monkeypatch.setattr(service, "get_config", fake_config)

        stats = await service.get_server_stats()

        assert stats == {
            "cpu_percent": 12.0,
            "memory": {"total": 10, "used": 4, "percent": 40.0, "available": 6},
            "disk": {"total": 20, "used": 5, "percent": 25.0},
            "docker": {"running": 2, "max_allowed": 5},
        }


class TestDockerCount:
    async def test_success(self, service, monkeypatch):
        monkeypatch.setattr(
            rc_module.ResourceConfigService,
            "_count_docker_containers",
            staticmethod(lambda: 4),
        )

        assert await service._get_docker_container_count() == 4

    async def test_error_logs_and_returns_zero(self, service, monkeypatch):
        from unittest.mock import MagicMock

        fake_logger = MagicMock()
        monkeypatch.setattr(rc_module, "logger", fake_logger)
        monkeypatch.setattr(
            rc_module.ResourceConfigService,
            "_count_docker_containers",
            staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("no docker"))),
        )

        assert await service._get_docker_container_count() == 0
        assert fake_logger.warning.called

    def test_real_counter_uses_docker_client(self, monkeypatch):
        class Client:
            containers = type("C", (), {"list": lambda self: [1, 2, 3]})()

        fake_docker = type("D", (), {"from_env": staticmethod(lambda: Client())})
        monkeypatch.setitem(__import__("sys").modules, "docker", fake_docker)

        assert rc_module.ResourceConfigService._count_docker_containers() == 3
