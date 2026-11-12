"""app.main 分支覆盖：lifespan、配置校验、静态路由与恢复逻辑。"""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.responses import FileResponse

import app.main as module


class _Cache:
    backend = "memory"

    async def close(self):
        return None


class _Guardian:
    instances = []

    def __init__(self, check_interval=10):
        self.check_interval = check_interval
        self.scanned = False
        self.monitoring = False
        self.shut_down = False
        _Guardian.instances.append(self)

    async def scan_and_learn(self, auto_enable_trusted=False):
        self.scanned = auto_enable_trusted

    async def start_monitoring_enabled_services(self):
        self.monitoring = True

    async def shutdown(self):
        self.shut_down = True


class _ShutdownManager:
    def __init__(self):
        self.is_draining = False
        self.connections = 0
        self.signals = 0
        self.shutdown_called = False

    def setup_signal_handlers(self):
        self.signals += 1

    def increment_connections(self):
        self.connections += 1

    def decrement_connections(self):
        self.connections -= 1

    async def shutdown_async(self):
        self.shutdown_called = True


def test_validate_production_configs_non_production(monkeypatch):
    monkeypatch.setattr(
        module.settings, "ENV", "development", raising=False
    )
    module._validate_production_config_files()

def test_validate_production_configs_all_present(tmp_path, monkeypatch):
    for relative in module._REQUIRED_PRODUCTION_CONFIGS:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x")
    monkeypatch.setattr(module.settings, "ENV", "production", raising=False)
    monkeypatch.setattr(module, "BASE_DIR", tmp_path)
    module._validate_production_config_files()


def test_validate_production_configs_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(module.settings, "ENV", "production", raising=False)
    monkeypatch.setattr(module, "BASE_DIR", tmp_path)
    with pytest.raises(RuntimeError) as excinfo:
        module._validate_production_config_files()
    assert "生产环境缺少必需配置文件" in str(excinfo.value)


@pytest.mark.asyncio
async def test_warm_up_database_pool_success(monkeypatch):
    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def execute(self, _stmt):
            return None

    monkeypatch.setattr(module, "async_session", lambda: _Session())
    await module._warm_up_database_pool()


@pytest.mark.asyncio
async def test_warm_up_database_pool_failure(monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(module, "async_session", boom)
    await module._warm_up_database_pool()


@pytest.mark.asyncio
async def test_cleanup_http_client_success(monkeypatch):
    called = []
    monkeypatch.setattr(
        "app.utils.http_client.close_http_client",
        lambda: _record(called),
    )
    await module._cleanup_http_client()
    assert called == [True]


async def _record(target):
    target.append(True)


@pytest.mark.asyncio
async def test_cleanup_http_client_failure(monkeypatch):
    def boom():
        raise RuntimeError("close failed")

    monkeypatch.setattr("app.utils.http_client.close_http_client", boom)
    await module._cleanup_http_client()


@pytest.mark.asyncio
async def test_clear_history_table_success(monkeypatch):
    class _Session:
        def __init__(self):
            self.committed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def execute(self, _stmt):
            return None

        async def commit(self):
            self.committed = True

        async def rollback(self):
            raise AssertionError("rollback should not run")

    session = _Session()
    monkeypatch.setattr(module, "async_session", lambda: session)
    await module.clear_history_table()
    assert session.committed is True


@pytest.mark.asyncio
async def test_clear_history_table_failure(monkeypatch):
    class _Session:
        def __init__(self):
            self.rolled_back = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def execute(self, _stmt):
            raise RuntimeError("delete failed")

        async def commit(self):
            raise AssertionError("commit should not run")

        async def rollback(self):
            self.rolled_back = True

    session = _Session()
    monkeypatch.setattr(module, "async_session", lambda: session)
    await module.clear_history_table()
    assert session.rolled_back is True


def _patch_provider_dependencies(monkeypatch, keys, sync_calls, sync_error=None):
    class _ApikeyManager:
        def get_all_enabled_keys(self):
            return keys

    async def fake_sync(provider, api_key, user_id):
        if sync_error:
            raise sync_error
        sync_calls.append((provider, api_key, user_id))

    monkeypatch.setattr(
        "app.services.apikey_manager.get_apikey_manager",
        lambda: _ApikeyManager(),
    )

    class _CustomManager:
        pass

    monkeypatch.setattr(
        "app.services.custom_provider_manager.get_custom_provider_manager",
        lambda: _CustomManager(),
    )
    monkeypatch.setattr(
        "app.api.v1.apikey._PROVIDER_BASE_URLS", {}, raising=False
    )
    monkeypatch.setattr(
        "app.api.v1.apikey._OPENAI_COMPAT_PROVIDERS", {"openai"}, raising=False
    )
    monkeypatch.setattr("app.api.v1.apikey._sync_provider_models", fake_sync)


@pytest.mark.asyncio
async def test_restore_user_providers_no_keys(monkeypatch):
    sync_calls = []
    _patch_provider_dependencies(monkeypatch, [], sync_calls)
    await module._restore_user_providers()
    assert sync_calls == []


@pytest.mark.asyncio
async def test_restore_user_providers_no_compatible_provider(monkeypatch):
    sync_calls = []
    _patch_provider_dependencies(
        monkeypatch, [("u1", "t", "other", "key")], sync_calls
    )
    await module._restore_user_providers()
    assert sync_calls == []


@pytest.mark.asyncio
async def test_restore_user_providers_syncs_each_user(monkeypatch):
    sync_calls = []
    keys = [
        ("u1", "t1", "openai", "k1"),
        ("u2", "t2", "openai", "k2"),
        ("u1", "t3", "openai", "k3"),
    ]
    _patch_provider_dependencies(monkeypatch, keys, sync_calls)
    await module._restore_user_providers()
    assert sync_calls == [("openai", "k1", "u1"), ("openai", "k2", "u2")]


@pytest.mark.asyncio
async def test_restore_user_providers_swallows_errors(monkeypatch):
    sync_calls = []
    _patch_provider_dependencies(
        monkeypatch,
        [("u1", "t", "openai", "k")],
        sync_calls,
        sync_error=RuntimeError("sync error"),
    )
    await module._restore_user_providers()


@pytest.mark.asyncio
async def test_lifespan_full_flow(monkeypatch, tmp_path):
    shutdown = _ShutdownManager()
    app_state = SimpleNamespace()
    app = SimpleNamespace(state=app_state)
    guardian = _Guardian()
    events = []

    monkeypatch.setattr(module, "shutdown_manager", shutdown)
    monkeypatch.setattr(module, "settings", SimpleNamespace(
        REDIS_URL="redis://x", ENABLE_SCHEDULER=True, ENV="development"
    ))
    monkeypatch.setattr(module, "_validate_production_config_files", lambda: events.append("validate"))
    monkeypatch.setattr(module.Path, "mkdir", lambda *a, **k: None)

    async def fake_cache(redis_url=None):
        events.append(("cache", redis_url))
        return _Cache()

    async def fake_warm():
        events.append("warm")

    async def fake_migrations():
        events.append("migrations")

    async def fake_restore():
        events.append("restore")

    async def fake_cleanup():
        events.append("cleanup")

    monkeypatch.setattr(module, "get_cache_manager", fake_cache)
    monkeypatch.setattr(module, "_warm_up_database_pool", fake_warm)
    monkeypatch.setattr(module, "run_async_migrations", fake_migrations)
    monkeypatch.setattr(module, "_restore_user_providers", fake_restore)
    monkeypatch.setattr(module, "_cleanup_http_client", fake_cleanup)
    monkeypatch.setattr(module, "start_scheduler", lambda: events.append("scheduler"))
    monkeypatch.setattr(module, "stop_scheduler", lambda: events.append("stop"))
    monkeypatch.setattr(module, "AsyncSmartGuardian", lambda **kwargs: guardian)

    ctx = module.lifespan(app)
    async with ctx:
        assert app_state.cache.backend == "memory"
        assert app_state.guardian is guardian
        assert app_state.shutdown_manager is shutdown

    assert shutdown.signals == 1
    assert guardian.scanned is True
    assert guardian.monitoring is True
    assert guardian.shut_down is True
    assert shutdown.shutdown_called is True
    assert "stop" in events and "cleanup" in events


@pytest.mark.asyncio
async def test_lifespan_without_redis_or_scheduler_and_error_paths(monkeypatch):
    shutdown = _ShutdownManager()
    app = SimpleNamespace(state=SimpleNamespace())
    guardian = _Guardian()

    monkeypatch.setattr(module, "shutdown_manager", shutdown)
    monkeypatch.setattr(module, "settings", SimpleNamespace(
        REDIS_URL="", ENABLE_SCHEDULER=False, ENV="development"
    ))
    monkeypatch.setattr(module, "_validate_production_config_files", lambda: None)
    monkeypatch.setattr(module.Path, "mkdir", lambda *a, **k: None)

    async def fake_cache(redis_url=None):
        return _Cache()

    async def broken_migrations():
        raise RuntimeError("migration failed")

    async def warm_ok():
        return None

    async def fake_restore():
        return None

    async def fake_cleanup():
        return None

    monkeypatch.setattr(module, "get_cache_manager", fake_cache)
    monkeypatch.setattr(module, "_warm_up_database_pool", warm_ok)
    monkeypatch.setattr(module, "run_async_migrations", broken_migrations)
    monkeypatch.setattr(module, "_restore_user_providers", fake_restore)
    monkeypatch.setattr(module, "_cleanup_http_client", fake_cleanup)
    monkeypatch.setattr(module, "AsyncSmartGuardian", lambda **kwargs: guardian)

    ctx = module.lifespan(app)
    async with ctx:
        pass

    assert shutdown.shutdown_called is True


@pytest.mark.asyncio
async def test_lifespan_scheduler_start_failure(monkeypatch):
    shutdown = _ShutdownManager()
    app = SimpleNamespace(state=SimpleNamespace())
    guardian = _Guardian()

    monkeypatch.setattr(module, "shutdown_manager", shutdown)
    monkeypatch.setattr(module, "settings", SimpleNamespace(
        REDIS_URL=None, ENABLE_SCHEDULER=True, ENV="development"
    ))
    monkeypatch.setattr(module, "_validate_production_config_files", lambda: None)
    monkeypatch.setattr(module.Path, "mkdir", lambda *a, **k: None)

    async def fake_cache(redis_url=None):
        return _Cache()

    async def fake_none():
        return None

    def broken_scheduler():
        raise RuntimeError("scheduler down")

    stop_called = []
    monkeypatch.setattr(module, "get_cache_manager", fake_cache)
    monkeypatch.setattr(module, "_warm_up_database_pool", fake_none)
    monkeypatch.setattr(module, "run_async_migrations", fake_none)
    monkeypatch.setattr(module, "_restore_user_providers", fake_none)
    monkeypatch.setattr(module, "_cleanup_http_client", fake_none)
    monkeypatch.setattr(module, "start_scheduler", broken_scheduler)
    monkeypatch.setattr(module, "stop_scheduler", lambda: stop_called.append(True))
    monkeypatch.setattr(module, "AsyncSmartGuardian", lambda **kwargs: guardian)

    ctx = module.lifespan(app)
    async with ctx:
        pass

    assert stop_called == []


@pytest.mark.asyncio
async def test_lifespan_cache_close_failure(monkeypatch):
    shutdown = _ShutdownManager()
    app = SimpleNamespace(state=SimpleNamespace())
    guardian = _Guardian()

    class _FailingCache(_Cache):
        async def close(self):
            raise RuntimeError("close failed")

    monkeypatch.setattr(module, "shutdown_manager", shutdown)
    monkeypatch.setattr(module, "settings", SimpleNamespace(
        REDIS_URL=None, ENABLE_SCHEDULER=False, ENV="development"
    ))
    monkeypatch.setattr(module, "_validate_production_config_files", lambda: None)
    monkeypatch.setattr(module.Path, "mkdir", lambda *a, **k: None)

    async def fake_cache(redis_url=None):
        return _FailingCache()

    async def fake_none():
        return None

    monkeypatch.setattr(module, "get_cache_manager", fake_cache)
    monkeypatch.setattr(module, "_warm_up_database_pool", fake_none)
    monkeypatch.setattr(module, "run_async_migrations", fake_none)
    monkeypatch.setattr(module, "_restore_user_providers", fake_none)
    monkeypatch.setattr(module, "_cleanup_http_client", fake_none)
    monkeypatch.setattr(module, "AsyncSmartGuardian", lambda **kwargs: guardian)

    import app.utils.cache as cache_module

    cache_manager = _FailingCache()
    monkeypatch.setattr(cache_module, "_cache_manager", cache_manager)

    ctx = module.lifespan(app)
    async with ctx:
        pass


@pytest.mark.asyncio
async def test_lifespan_closes_existing_cache_manager(monkeypatch):
    shutdown = _ShutdownManager()
    app = SimpleNamespace(state=SimpleNamespace())
    guardian = _Guardian()
    closed = []

    class _ClosableCache(_Cache):
        async def close(self):
            closed.append(True)

    import app.utils.cache as cache_module

    monkeypatch.setattr(cache_module, "_cache_manager", _ClosableCache())
    monkeypatch.setattr(module, "shutdown_manager", shutdown)
    monkeypatch.setattr(module, "settings", SimpleNamespace(
        REDIS_URL=None, ENABLE_SCHEDULER=False, ENV="development"
    ))
    monkeypatch.setattr(module, "_validate_production_config_files", lambda: None)
    monkeypatch.setattr(module.Path, "mkdir", lambda *a, **k: None)

    async def fake_cache(redis_url=None):
        return _Cache()

    async def fake_none():
        return None

    monkeypatch.setattr(module, "get_cache_manager", fake_cache)
    monkeypatch.setattr(module, "_warm_up_database_pool", fake_none)
    monkeypatch.setattr(module, "run_async_migrations", fake_none)
    monkeypatch.setattr(module, "_restore_user_providers", fake_none)
    monkeypatch.setattr(module, "_cleanup_http_client", fake_none)
    monkeypatch.setattr(module, "AsyncSmartGuardian", lambda **kwargs: guardian)

    ctx = module.lifespan(app)
    async with ctx:
        pass

    assert closed == [True]


@pytest.mark.asyncio
async def test_drain_mode_middleware_blocks_when_draining(monkeypatch):
    shutdown = _ShutdownManager()
    shutdown.is_draining = True
    monkeypatch.setattr(module, "shutdown_manager", shutdown)
    called = []

    async def call_next(_request):
        called.append(True)
        return "response"

    response = await module.drain_mode_middleware(SimpleNamespace(), call_next)
    assert response.status_code == 503
    assert called == []


@pytest.mark.asyncio
async def test_drain_mode_middleware_tracks_connections(monkeypatch):
    shutdown = _ShutdownManager()
    monkeypatch.setattr(module, "shutdown_manager", shutdown)

    async def call_next(_request):
        return "ok"

    assert await module.drain_mode_middleware(SimpleNamespace(), call_next) == "ok"
    assert shutdown.connections == 0


@pytest.mark.asyncio
async def test_drain_mode_middleware_decrements_on_error(monkeypatch):
    shutdown = _ShutdownManager()
    monkeypatch.setattr(module, "shutdown_manager", shutdown)

    async def call_next(_request):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await module.drain_mode_middleware(SimpleNamespace(), call_next)
    assert shutdown.connections == 0


def test_dist_index_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "DIST_PATH", str(tmp_path))
    with pytest.raises(HTTPException) as excinfo:
        module._dist_index_or_404()
    assert excinfo.value.status_code == 404


def test_dist_index_present_returns_file(tmp_path, monkeypatch):
    index = tmp_path / "index.html"
    index.write_text("html")
    monkeypatch.setattr(module, "DIST_PATH", str(tmp_path))
    response = module._dist_index_or_404()
    assert isinstance(response, FileResponse)


@pytest.mark.asyncio
async def test_serve_vue_returns_index(tmp_path, monkeypatch):
    index = tmp_path / "index.html"
    index.write_text("html")
    monkeypatch.setattr(module, "DIST_PATH", str(tmp_path))
    assert isinstance(await module.serve_vue(), FileResponse)


@pytest.mark.asyncio
async def test_serve_vue_routes_rejects_api(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "DIST_PATH", str(tmp_path))
    with pytest.raises(HTTPException) as excinfo:
        await module.serve_vue_routes("api/v1/health")
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_serve_vue_routes_serves_existing_file(tmp_path, monkeypatch):
    asset = tmp_path / "assets" / "app.js"
    asset.parent.mkdir(parents=True)
    asset.write_text("js")
    (tmp_path / "index.html").write_text("html")
    monkeypatch.setattr(module, "DIST_PATH", str(tmp_path))
    response = await module.serve_vue_routes("assets/app.js")
    assert isinstance(response, FileResponse)


@pytest.mark.asyncio
async def test_serve_vue_routes_blocks_path_traversal(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("html")
    secret = tmp_path / "secret.txt"
    secret.write_text("secret")
    monkeypatch.setattr(module, "DIST_PATH", str(dist))
    response = await module.serve_vue_routes("../secret.txt")
    assert isinstance(response, FileResponse)
    assert Path(response.path).name == "index.html"


@pytest.mark.asyncio
async def test_serve_vue_routes_falls_back_to_index(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("html")
    monkeypatch.setattr(module, "DIST_PATH", str(tmp_path))
    response = await module.serve_vue_routes("some/route")
    assert Path(response.path).name == "index.html"
