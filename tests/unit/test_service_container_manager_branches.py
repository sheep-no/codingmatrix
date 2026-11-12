"""ServiceContainerManager 分支覆盖：缓存复用、启动回滚、健康检查与环境变量。"""

import asyncio
import time
from types import SimpleNamespace

import pytest

import app.utils.service_container_manager as scm
from app.utils.service_container_manager import (
    HEALTH_CACHE_TTL,
    ServiceContainerManager,
    _HealthCacheEntry,
    detect_project_services,
)


class _Container:
    def __init__(self, container_id="cid-r", status="running", exit_code=0):
        self.id = container_id
        self.status = status
        self.exit_code = exit_code
        self.stopped = False
        self.exec_calls = []
        self.stop_error = None

    def stop(self, timeout=5):
        if self.stop_error:
            raise self.stop_error
        self.stopped = True

    def exec_run(self, cmd):
        self.exec_calls.append(cmd)
        return self


class _Containers:
    def __init__(self, container=None, run_error=None):
        self.container = container or _Container()
        self.run_error = run_error
        self.get_error = None
        self.run_calls = []

    def run(self, **kwargs):
        if self.run_error:
            raise self.run_error
        self.run_calls.append(kwargs)
        return self.container

    def get(self, container_id):
        if self.get_error:
            raise self.get_error
        return self.container


class _Client:
    def __init__(self, container=None, run_error=None):
        self.container = container or _Container()
        self.containers = _Containers(self.container, run_error)


def test_health_cache_entry_alive(monkeypatch):
    entry = _HealthCacheEntry("cid", {6379: 6380}, {"A": "B"})
    assert entry.is_alive() is True
    assert entry.host == "localhost"

    monkeypatch.setattr(
        scm, "time", SimpleNamespace(time=lambda: entry.timestamp + HEALTH_CACHE_TTL + 1)
    )
    assert entry.is_alive() is False


@pytest.mark.asyncio
async def test_start_service_containers_without_client():
    manager = ServiceContainerManager()
    assert await manager.start_service_containers(["redis"]) == {}


@pytest.mark.asyncio
async def test_start_service_containers_unknown_service_only():
    manager = ServiceContainerManager()
    client = _Client()
    result = await manager.start_service_containers(["unknown"], client)
    assert result == {}
    assert client.containers.run_calls == []


@pytest.mark.asyncio
async def test_start_service_containers_reuses_cached_container(monkeypatch):
    manager = ServiceContainerManager()
    client = _Client()
    manager._health_cache["redis"] = _HealthCacheEntry(
        container_id="cid", port_mapping={6379: 16379}, env_vars={"REDIS_URL": "x"}
    )
    started = []

    async def fake_start(*_args):
        started.append(True)
        return {"should": "not-happen"}

    monkeypatch.setattr(manager, "_start_and_register", fake_start)
    result = await manager.start_service_containers(["redis"], client)
    assert started == []
    assert result["redis"]["port"] == 16379
    assert result["redis"]["env_vars"] == {"REDIS_URL": "x"}
    assert manager._running_containers["redis"] == "cid"


@pytest.mark.asyncio
async def test_start_service_containers_drops_dead_cached_container(monkeypatch):
    manager = ServiceContainerManager()
    client = _Client(_Container(status="exited"))
    manager._health_cache["redis"] = _HealthCacheEntry(
        container_id="cid", port_mapping={6379: 16379}, env_vars={}
    )
    started = []

    async def fake_start(svc, _config, _client):
        started.append(svc)
        return {"host": "localhost", "port": 16380, "container_id": "new"}

    monkeypatch.setattr(manager, "_start_and_register", fake_start)
    result = await manager.start_service_containers(["redis"], client)
    assert started == ["redis"]
    assert result["redis"]["port"] == 16380


@pytest.mark.asyncio
async def test_start_service_containers_records_exceptions_and_empty_results(monkeypatch):
    manager = ServiceContainerManager()
    client = _Client()

    async def fake_start(svc, _config, _client):
        if svc == "redis":
            raise RuntimeError("boom")
        return None

    monkeypatch.setattr(manager, "_start_and_register", fake_start)
    result = await manager.start_service_containers(["redis", "postgresql"], client)
    assert result == {}


@pytest.mark.asyncio
async def test_start_and_register_without_container_id():
    manager = ServiceContainerManager()

    async def no_container(*_args):
        return None

    manager._start_container = no_container
    result = await manager._start_and_register("redis", {"ports": {6379: 6379}}, _Client())
    assert result is None


@pytest.mark.asyncio
async def test_start_and_register_allocates_when_mapping_missing(monkeypatch):
    manager = ServiceContainerManager()
    monkeypatch.setattr(manager, "_find_available_port", lambda preferred: preferred + 100)
    monkeypatch.setattr(manager, "_generate_test_env_vars", lambda s, p: {"P": str(p)})

    async def start(*_args):
        return "cid-1"

    manager._start_container = start
    info = await manager._start_and_register(
        "redis", {"ports": {6379: 6379}}, _Client()
    )
    assert info["port"] == 6479
    assert manager._container_ports["redis"] == {6379: 6479}
    assert manager._health_cache["redis"].container_id == "cid-1"


@pytest.mark.asyncio
async def test_start_container_success(monkeypatch):
    manager = ServiceContainerManager()
    client = _Client(_Container("cid-x"))
    monkeypatch.setattr(manager, "_find_available_port", lambda p: p)

    async def healthy(*_args):
        return True

    monkeypatch.setattr(manager, "_wait_for_health_single", healthy)
    container_id = await manager._start_container(
        "redis", {"image": "redis:7", "ports": {6379: 6379}}, client
    )
    assert container_id == "cid-x"
    assert manager._container_ports["redis"] == {6379: 6379}
    assert 6379 in manager._allocated_ports
    assert client.containers.run_calls[0]["name"].startswith("test-redis-")


@pytest.mark.asyncio
async def test_start_container_health_failure_rolls_back(monkeypatch):
    manager = ServiceContainerManager()
    client = _Client(_Container("cid-x"))
    monkeypatch.setattr(manager, "_find_available_port", lambda p: p + 1)

    async def unhealthy(*_args):
        return False

    monkeypatch.setattr(manager, "_wait_for_health_single", unhealthy)
    container_id = await manager._start_container(
        "redis", {"image": "redis:7", "ports": {6379: 6379}}, client
    )
    assert container_id is None
    assert client.container.stopped is True
    assert "redis" not in manager._container_ports


@pytest.mark.asyncio
async def test_start_container_exception_returns_none(monkeypatch):
    manager = ServiceContainerManager()
    client = _Client(run_error=RuntimeError("docker down"))
    monkeypatch.setattr(manager, "_find_available_port", lambda p: p)
    assert (
        await manager._start_container(
            "redis", {"image": "redis:7", "ports": {6379: 6379}}, client
        )
        is None
    )


@pytest.mark.asyncio
async def test_stop_container_success_and_failure():
    manager = ServiceContainerManager()
    client = _Client()
    assert await manager._stop_container(client, "cid-r", "redis") is True
    assert client.container.stopped is True

    client.container.stop_error = RuntimeError("stop fail")
    assert await manager._stop_container(client, "cid-r", "redis") is False


@pytest.mark.asyncio
async def test_wait_for_health_single_tcp_timeout(monkeypatch):
    manager = ServiceContainerManager()
    times = iter([0, 0, 100])
    monkeypatch.setattr(scm, "time", SimpleNamespace(time=lambda: next(times, 100)))

    async def closed(*_args):
        return False

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(manager, "_port_is_open_async", closed)
    monkeypatch.setattr(scm.asyncio, "sleep", no_sleep)
    ok = await manager._wait_for_health_single(
        "redis", "cid", {"health_port": 6379, "startup_timeout": 1}, _Client()
    )
    assert ok is False


@pytest.mark.asyncio
async def test_wait_for_health_single_tcp_only_no_cmd(monkeypatch):
    manager = ServiceContainerManager()

    async def opened(*_args):
        return True

    monkeypatch.setattr(manager, "_port_is_open_async", opened)
    ok = await manager._wait_for_health_single(
        "redis", "cid", {"health_port": 6379, "startup_timeout": 1}, _Client()
    )
    assert ok is True


@pytest.mark.asyncio
async def test_wait_for_health_single_exec_success(monkeypatch):
    manager = ServiceContainerManager()
    client = _Client(_Container("cid", exit_code=0))

    async def opened(*_args):
        return True

    monkeypatch.setattr(manager, "_port_is_open_async", opened)
    ok = await manager._wait_for_health_single(
        "redis",
        "cid",
        {"health_port": 6379, "startup_timeout": 1, "health_cmd": "ping"},
        client,
    )
    assert ok is True
    assert client.container.exec_calls == ["ping"]


@pytest.mark.asyncio
async def test_wait_for_health_single_exec_retries_then_fails(monkeypatch):
    manager = ServiceContainerManager()
    client = _Client(_Container("cid", exit_code=1))

    async def opened(*_args):
        return True

    async def no_sleep(_seconds):
        return None

    times = iter([0, 0, 0, 0, 0, 100])
    monkeypatch.setattr(scm, "time", SimpleNamespace(time=lambda: next(times, 100)))
    monkeypatch.setattr(manager, "_port_is_open_async", opened)
    monkeypatch.setattr(scm.asyncio, "sleep", no_sleep)
    ok = await manager._wait_for_health_single(
        "redis",
        "cid",
        {"health_port": 6379, "startup_timeout": 1, "health_cmd": "ping"},
        client,
    )
    assert ok is False
    assert client.container.exec_calls


@pytest.mark.asyncio
async def test_wait_for_health_single_exec_exception(monkeypatch):
    manager = ServiceContainerManager()
    client = _Client()
    client.containers.get_error = RuntimeError("gone")

    async def opened(*_args):
        return True

    async def no_sleep(_seconds):
        return None

    times = iter([0, 0, 0, 0, 0, 100])
    monkeypatch.setattr(scm, "time", SimpleNamespace(time=lambda: next(times, 100)))
    monkeypatch.setattr(manager, "_port_is_open_async", opened)
    monkeypatch.setattr(scm.asyncio, "sleep", no_sleep)
    ok = await manager._wait_for_health_single(
        "redis",
        "cid",
        {"health_port": 6379, "startup_timeout": 1, "health_cmd": "ping"},
        client,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_wait_for_health_aggregates(monkeypatch):
    manager = ServiceContainerManager()
    calls = []

    async def fake_single(service_name, *_args):
        calls.append(service_name)
        return service_name != "mysql"

    monkeypatch.setattr(manager, "_wait_for_health_single", fake_single)
    info = {"redis": {"container_id": "a"}, "mysql": {"container_id": "b"}}
    assert await manager.wait_for_health(info) is False
    assert calls == ["redis", "mysql"]

    manager._health_cache["mysql"] = _HealthCacheEntry("b", {3306: 3306}, {})
    assert await manager.wait_for_health(info) is True


@pytest.mark.asyncio
async def test_wait_for_health_skips_unknown_service(monkeypatch):
    manager = ServiceContainerManager()
    monkeypatch.setattr(
        manager, "_wait_for_health_single", lambda *a: pytest.fail("should not run")
    )
    assert await manager.wait_for_health({"unknown": {}}) is True


@pytest.mark.asyncio
async def test_port_is_open_async_paths(monkeypatch):
    writer = SimpleNamespace(
        close=lambda: None,
        wait_closed=lambda: _async_none(),
    )

    async def opened(*_args, **_kwargs):
        return object(), writer

    monkeypatch.setattr(scm.asyncio, "open_connection", opened)
    assert await ServiceContainerManager._port_is_open_async(127, 0, 0, 1, 1) is True

    async def refuse(*_args, **_kwargs):
        raise OSError("refused")

    monkeypatch.setattr(scm.asyncio, "open_connection", refuse)
    assert await ServiceContainerManager._port_is_open_async(127, 0, 0, 1, 1) is False


async def _async_none():
    return None


@pytest.mark.asyncio
async def test_port_is_open_async_wait_closed_error(monkeypatch):
    class _Writer:
        def close(self):
            pass

        async def wait_closed(self):
            raise RuntimeError("late")

    async def opened(*_args, **_kwargs):
        return object(), _Writer()

    monkeypatch.setattr(scm.asyncio, "open_connection", opened)
    assert await ServiceContainerManager._port_is_open_async(1, 1, 1, 1, 1) is True


def test_verify_container_alive_paths():
    manager = ServiceContainerManager()
    assert manager._verify_container_alive("cid", _Client(_Container(status="running"))) is True
    assert manager._verify_container_alive("cid", _Client(_Container(status="exited"))) is False

    client = _Client()
    client.containers.get_error = RuntimeError("missing")
    assert manager._verify_container_alive("cid", client) is False


def test_generate_test_env_vars_merges():
    manager = ServiceContainerManager()
    info = {
        "redis": {"env_vars": {"A": "1"}},
        "mysql": {"env_vars": {"B": "2"}},
        "empty": {},
    }
    assert manager.generate_test_env_vars(info) == {"A": "1", "B": "2"}


def test_find_available_port_skips_allocated(monkeypatch):
    manager = ServiceContainerManager()
    manager._allocated_ports.add(1000)
    assert manager._find_available_port(1000) > 1000


def test_find_available_port_bind_failure(monkeypatch):
    manager = ServiceContainerManager()

    class _Socket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def bind(self, _addr):
            raise OSError("in use")

    monkeypatch.setattr("socket.socket", lambda *a, **k: _Socket())
    with pytest.raises(RuntimeError):
        manager._find_available_port(65535)


def test_generate_test_env_vars_replaces_ports():
    manager = ServiceContainerManager()
    env = manager._generate_test_env_vars("redis", {6379: 16379})
    assert env
    assert all("6379" not in value or "16379" in value for value in env.values())


def test_generate_test_env_vars_unknown_service():
    manager = ServiceContainerManager()
    assert manager._generate_test_env_vars("nope", {}) == {}


def test_generate_test_env_vars_template_error(monkeypatch):
    manager = ServiceContainerManager()

    def boom(_name):
        raise RuntimeError("template down")

    monkeypatch.setattr(
        "app.agent.service_config_templates.get_service_template", boom
    )
    assert manager._generate_test_env_vars("redis", {}) == {}


@pytest.mark.asyncio
async def test_cleanup_containers_without_client():
    manager = ServiceContainerManager()
    manager._running_containers["redis"] = "cid"
    await manager.cleanup_containers()
    assert manager._running_containers == {"redis": "cid"}


@pytest.mark.asyncio
async def test_cleanup_all_delegates(monkeypatch):
    manager = ServiceContainerManager()
    called = []

    async def cleanup(_client):
        called.append(True)

    monkeypatch.setattr(manager, "cleanup_containers", cleanup)
    await manager.cleanup_all(_Client())
    assert called == [True]


def test_get_running_services_returns_copy():
    manager = ServiceContainerManager()
    manager._running_containers["redis"] = "cid"
    copy = manager.get_running_services()
    copy["mysql"] = "other"
    assert "mysql" not in manager._running_containers


def _project(tmp_path, **files):
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return tmp_path


def test_detect_project_services_requirements(tmp_path):
    path = _project(
        tmp_path,
        **{"requirements.txt": "# comment\nredis==5.0\npsycopg2-binary>=2\npymongo\n"},
    )
    services = detect_project_services(path)
    assert "redis" in services
    assert "postgresql" in services
    assert "mongodb" in services


def test_detect_project_services_env_file(tmp_path):
    path = _project(
        tmp_path,
        **{
            ".env.example": (
                "# REDIS_URL=redis://x\nREDIS_URL=redis://y\n"
                "DATABASE_URL=postgres://z\nREDIS_HOST=localhost\nnot-an-assignment\n"
            ),
        },
    )
    services = detect_project_services(path)
    assert services == ["redis", "postgresql"]


def test_detect_project_services_compose_image_lines(tmp_path):
    compose = (
        "services:\n"
        "  cache:\n"
        "    image: redis:7-alpine\n"
        "  db:\n"
        "    image: postgres:16\n"
        "    # image: mysql:8\n"
    )
    path = _project(tmp_path, **{"docker-compose.yml": compose})
    services = detect_project_services(path)
    assert "redis" in services
    assert "postgresql" in services
    assert "mysql" not in services


def test_detect_project_services_compose_yaml_variant(tmp_path):
    path = _project(
        tmp_path,
        **{"docker-compose.yaml": "services:\n  mq:\n    image: rabbitmq:3\n"},
    )
    assert detect_project_services(path) == ["rabbitmq"]


def test_detect_project_services_unreadable_files(tmp_path, monkeypatch):
    path = _project(
        tmp_path,
        **{
            "requirements.txt": "redis",
            ".env.example": "REDIS_URL=x",
            "docker-compose.yml": "image: redis",
        },
    )

    def boom(*_args, **_kwargs):
        raise OSError("unreadable")

    monkeypatch.setattr(scm.Path, "read_text", boom)
    assert detect_project_services(path) == []


def test_detect_project_services_empty_project(tmp_path):
    assert detect_project_services(tmp_path) == []
