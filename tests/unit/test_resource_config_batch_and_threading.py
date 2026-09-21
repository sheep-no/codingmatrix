"""资源配置批量更新与资源采样回归。

- batch_update_configs 原在循环内逐个 SELECT（N+1），且在 commit 前改缓存，
  提交失败时缓存与数据库漂移。
- get_server_stats 的 psutil/docker 调用均为同步阻塞，需移出事件循环。
"""

import importlib
import threading

import pytest

rc_module = importlib.import_module("app.services.resource_config")


@pytest.fixture()
def service(monkeypatch):
    monkeypatch.setattr(rc_module.ResourceConfigService, "_instance", None)
    return rc_module.ResourceConfigService()


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _Row:
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.updated_by = None


class _Session:
    def __init__(self, rows, fail_commit=False):
        self.rows = rows
        self.fail_commit = fail_commit
        self.statements = []
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self.rows)

    def add(self, instance):
        self.added.append(instance)

    async def commit(self):
        if self.fail_commit:
            raise RuntimeError("commit failed")


async def test_batch_update_uses_one_query(service, monkeypatch):
    rows = [_Row("a", "1"), _Row("b", "2")]
    session = _Session(rows)
    monkeypatch.setattr(rc_module, "async_session", lambda: session)

    assert await service.batch_update_configs({"a": "x", "b": "y"}) is True
    assert len(session.statements) == 1
    assert rows[0].value == "x"
    assert service._config_cache == {"a": "x", "b": "y"}


async def test_batch_update_keeps_cache_when_commit_fails(service, monkeypatch):
    session = _Session([_Row("a", "1")], fail_commit=True)
    monkeypatch.setattr(rc_module, "async_session", lambda: session)

    with pytest.raises(RuntimeError):
        await service.batch_update_configs({"a": "x"})

    assert service._config_cache == {}


async def test_get_server_stats_samples_off_event_loop(service, monkeypatch):
    import psutil

    threads = {}

    def fake_cpu(interval=None):
        threads["cpu"] = threading.get_ident()
        return 12.5

    def fake_memory():
        threads["memory"] = threading.get_ident()
        return type("M", (), {"total": 1, "used": 1, "percent": 1.0, "available": 1})()

    def fake_disk(_path):
        threads["disk"] = threading.get_ident()
        return type("D", (), {"total": 1, "used": 1, "percent": 1.0})()

    async def fake_config(key, default=None):
        return "5"

    monkeypatch.setattr(psutil, "cpu_percent", fake_cpu)
    monkeypatch.setattr(psutil, "virtual_memory", fake_memory)
    monkeypatch.setattr(psutil, "disk_usage", fake_disk)
    monkeypatch.setattr(service, "get_config", fake_config)
    monkeypatch.setattr(service, "_get_docker_container_count", _fake_count)

    stats = await service.get_server_stats()

    assert stats["cpu_percent"] == 12.5
    assert stats["docker"]["running"] == 3
    main_ident = threading.get_ident()
    # 采样发生在工作线程而非事件循环线程，即未阻塞事件循环
    assert threads["cpu"] != main_ident
    assert threads["memory"] != main_ident
    assert threads["disk"] != main_ident


async def _fake_count():
    return 3
