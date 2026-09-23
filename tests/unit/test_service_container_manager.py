"""ServiceContainerManager 回归测试（此前零覆盖）。

覆盖 SCM1（清理永不停止）、SCM2（健康失败放行）、SCM3（健康失败仍返回 id）、
SCM4（服务检测子串误报）、SCM5（同步 socket 阻塞）、SCM6（端口分配不验证）、
SCM7（startup_timeout 被截断）、SCM9（env 生成静默）以及端口映射/端口替换误伤。
"""
import asyncio

import pytest

import app.utils.service_container_manager as scm
from app.utils.service_container_manager import (
    ServiceContainerManager,
    detect_project_services,
)


class _FakeContainer:
    def __init__(self, container_id, exit_code=0, status="running"):
        self.id = container_id
        self.exit_code = exit_code
        self.status = status
        self.stopped = False
        self.exec_commands = []

    def stop(self, timeout=5):
        self.stopped = True

    def exec_run(self, cmd):
        self.exec_commands.append(cmd)
        return self


class _FakeContainers:
    def __init__(self, container):
        self._container = container
        self.run_kwargs = []
        self.run_error = None

    def run(self, **kwargs):
        if self.run_error:
            raise self.run_error
        self.run_kwargs.append(kwargs)
        return self._container

    def get(self, container_id):
        if container_id != self._container.id:
            raise KeyError(container_id)
        return self._container


class _FakeClient:
    def __init__(self, container=None):
        self.container = container or _FakeContainer("cid1234567890")
        self.containers = _FakeContainers(self.container)


@pytest.fixture
def free_port():
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


class TestCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_stops_all_started_containers(self):
        """SCM1：本批启动的容器必须被停止，不能因缓存命中而跳过"""
        manager = ServiceContainerManager()
        container = _FakeContainer("cid-1")
        client = _FakeClient(container)
        manager._running_containers["redis"] = container.id
        manager._health_cache["redis"] = scm._HealthCacheEntry(
            container_id=container.id, port_mapping={6379: 6379}, env_vars={}
        )

        await manager.cleanup_containers(client)

        assert container.stopped is True
        assert manager.get_running_services() == {}
        assert manager._health_cache == {}

    @pytest.mark.asyncio
    async def test_cleanup_without_client_is_noop(self):
        manager = ServiceContainerManager()
        manager._running_containers["redis"] = "cid-1"
        await manager.cleanup_containers(None)
        assert manager.get_running_services() == {"redis": "cid-1"}


class TestHealth:
    @pytest.mark.asyncio
    async def test_start_container_returns_none_and_stops_on_health_failure(
        self, monkeypatch
    ):
        """SCM3：健康检查失败不再返回 container_id，且回滚容器"""
        manager = ServiceContainerManager()
        container = _FakeContainer("cid-1")
        client = _FakeClient(container)

        async def unhealthy(*args, **kwargs):
            return False

        monkeypatch.setattr(manager, "_wait_for_health_single", unhealthy)

        result = await manager._start_container(
            "redis", {"image": "redis:7-alpine", "ports": {6379: 6379}, "env": {}}, client
        )

        assert result is None
        assert container.stopped is True

    @pytest.mark.asyncio
    async def test_exec_health_failure_returns_false(self, monkeypatch):
        """SCM2：exec 健康命令失败时返回 False，而不是「TCP 通即视为可用」"""
        manager = ServiceContainerManager()
        container = _FakeContainer("cid-1", exit_code=1)
        client = _FakeClient(container)

        async def tcp_open(*args, **kwargs):
            return True

        monkeypatch.setattr(manager, "_port_is_open_async", tcp_open)
        _install_fake_clock(monkeypatch)

        ok = await manager._wait_for_health_single(
            "redis",
            container.id,
            {"health_port": 6379, "startup_timeout": 10, "health_cmd": "redis-cli ping"},
            client,
        )

        assert ok is False
        assert container.exec_commands  # 确实执行了健康命令

    @pytest.mark.asyncio
    async def test_exec_health_success_returns_true(self, monkeypatch):
        manager = ServiceContainerManager()
        container = _FakeContainer("cid-1", exit_code=0)
        client = _FakeClient(container)

        async def tcp_open(*args, **kwargs):
            return True

        monkeypatch.setattr(manager, "_port_is_open_async", tcp_open)

        ok = await manager._wait_for_health_single(
            "redis",
            container.id,
            {"health_port": 6379, "startup_timeout": 10, "health_cmd": "redis-cli ping"},
            client,
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_startup_timeout_not_truncated(self, monkeypatch):
        """SCM7：startup_timeout=45 时 TCP 探测窗口应约 45s 而非 15s"""
        manager = ServiceContainerManager()

        async def tcp_closed(*args, **kwargs):
            return False

        monkeypatch.setattr(manager, "_port_is_open_async", tcp_closed)
        clock = _install_fake_clock(monkeypatch)

        ok = await manager._wait_for_health_single(
            "elasticsearch",
            "cid-1",
            {"health_port": 9200, "startup_timeout": 45, "health_cmd": ""},
            _FakeClient(),
        )

        assert ok is False
        # 每次循环 sleep 1s，45s 窗口应产生约 45 次睡眠，明显多于被截断的 15 次
        assert clock.sleep_calls >= 40


class TestPortAllocation:
    @pytest.mark.asyncio
    async def test_returned_port_matches_bound_port(self, monkeypatch):
        """端口映射只分配一次：返回 info/env 必须与实际绑定端口一致"""
        manager = ServiceContainerManager()
        client = _FakeClient(_FakeContainer("cid-1"))

        def alloc(preferred):
            port = preferred
            while port in manager._allocated_ports:
                port += 1
            return port

        monkeypatch.setattr(manager, "_find_available_port", alloc)

        async def healthy(*args, **kwargs):
            return True

        monkeypatch.setattr(manager, "_wait_for_health_single", healthy)

        info = await manager._start_and_register(
            "redis",
            {"image": "redis:7-alpine", "ports": {6379: 6379}, "env": {}},
            client,
        )

        bound = client.containers.run_kwargs[0]["ports"]
        assert bound == {6379: info["port"]}
        assert info["env_vars"]["REDIS_PORT"] == str(info["port"])
        assert str(info["port"]) in info["env_vars"]["REDIS_URL"]

    def test_find_available_port_skips_occupied_port(self, monkeypatch):
        """SCM6：端口被占用时继续向后探测，返回可绑定的端口"""
        import socket as real_socket

        busy = {6379, 6380}

        class _FakeSocket:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def bind(self, addr):
                if addr[1] in busy:
                    raise OSError("address in use")

        monkeypatch.setattr(real_socket, "socket", _FakeSocket)
        manager = ServiceContainerManager()
        assert manager._find_available_port(6379) == 6381


class TestPortReplacement:
    def test_port_substitution_does_not_damage_passwords(self, monkeypatch):
        """SCT4：端口替换只改独立端口数字，密码里的同名数字串不被误改"""

        class _Template:
            env_vars = {
                "SVC_URL": "scheme://user:pass5672word@localhost:5672/db",
                "SVC_PORT": "5672",
            }

        monkeypatch.setattr(
            "app.agent.service_config_templates.get_service_template",
            lambda name: _Template(),
        )
        manager = ServiceContainerManager()
        env = manager._generate_test_env_vars("rabbitmq", {5672: 5000})

        assert env["SVC_URL"] == "scheme://user:pass5672word@localhost:5000/db"
        assert env["SVC_PORT"] == "5000"

    def test_env_generation_logs_and_returns_empty_on_error(self, monkeypatch):
        """SCM9：模板查询异常不再静默，记录告警并返回空字典"""

        def boom(name):
            raise RuntimeError("template unavailable")

        monkeypatch.setattr(
            "app.agent.service_config_templates.get_service_template", boom
        )
        warnings = []

        class _RecordingLogger:
            def warning(self, msg, *args, **kwargs):
                warnings.append(msg % args if args else msg)

        monkeypatch.setattr(scm, "logger", _RecordingLogger())
        manager = ServiceContainerManager()
        env = manager._generate_test_env_vars("redis", {6379: 6380})

        assert env == {}
        assert any("测试环境变量" in msg for msg in warnings)


class TestPortProbe:
    @pytest.mark.asyncio
    async def test_port_is_open_async_detects_listener(self, free_port):
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", free_port)
        try:
            assert await ServiceContainerManager._port_is_open_async(
                127, 0, 0, 1, free_port
            )
        finally:
            server.close()
            await server.wait_closed()

    @pytest.mark.asyncio
    async def test_port_is_open_async_closed_port(self, free_port):
        assert not await ServiceContainerManager._port_is_open_async(
            127, 0, 0, 1, free_port
        )


class TestDetectProjectServices:
    def test_requirements_detection(self, tmp_path):
        (tmp_path / "requirements.txt").write_text(
            "fastapi\nredis==5.0.1\npsycopg2-binary>=2.9\n# pymongo\n",
            encoding="utf-8",
        )
        assert sorted(detect_project_services(tmp_path)) == ["postgresql", "redis"]

    def test_env_example_ignores_comments_and_matches_keys(self, tmp_path):
        (tmp_path / ".env.example").write_text(
            "# MONGODB_URL=mongodb://localhost:27017\nREDIS_URL=redis://localhost:6379/0\n",
            encoding="utf-8",
        )
        assert detect_project_services(tmp_path) == ["redis"]

    def test_compose_uses_image_not_service_name_or_comment(self, tmp_path):
        (tmp_path / "docker-compose.yml").write_text(
            "services:\n"
            "  mysql-db:\n"
            "    image: redis:7-alpine\n"
            "    # mongo backup note\n"
            "  api:\n"
            "    image: postgres:16-alpine\n",
            encoding="utf-8",
        )
        assert sorted(detect_project_services(tmp_path)) == ["postgresql", "redis"]

    def test_compose_yaml_extension_supported(self, tmp_path):
        (tmp_path / "docker-compose.yaml").write_text(
            "services:\n  mq:\n    image: rabbitmq:3-management-alpine\n",
            encoding="utf-8",
        )
        assert detect_project_services(tmp_path) == ["rabbitmq"]


def _install_fake_clock(monkeypatch):
    """以假时钟替换模块内 time/asyncio，使健康检查重试循环瞬时完成。"""

    class _Clock:
        def __init__(self):
            self.t = 0.0
            self.sleep_calls = 0

        def time(self):
            return self.t

    clock = _Clock()

    class _FakeTime:
        time = staticmethod(clock.time)

    async def fake_sleep(seconds):
        clock.sleep_calls += 1
        clock.t += seconds

    class _FakeAsyncio:
        sleep = staticmethod(fake_sleep)
        to_thread = staticmethod(asyncio.to_thread)
        wait_for = staticmethod(asyncio.wait_for)
        open_connection = staticmethod(asyncio.open_connection)
        TimeoutError = asyncio.TimeoutError

    monkeypatch.setattr(scm, "time", _FakeTime)
    monkeypatch.setattr(scm, "asyncio", _FakeAsyncio)
    return clock
