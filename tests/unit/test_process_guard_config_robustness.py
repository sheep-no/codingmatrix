"""AsyncProcessGuardian 配置缺失与多 PID 解析健壮性回归测试。

- PG5：`find_pid_by_port` 在 lsof 输出多个 PID 时 `int(整段)` 抛 ValueError
  并被吞掉，旧进程不被清理、重启 bind 失败。
- PG6：熔断持久化直接下标 `config['process_signature']`，缺键时 KeyError
  不在 except 白名单内，watch_port 协程直接崩溃退出。
- PG8：watch_port 开头直接下标 name/port/restart_cmd，缺键即崩溃。
"""
import asyncio

import pytest

from app.utils.process_guard import AsyncProcessGuardian


class _FakeProc:
    returncode = 0

    def __init__(self, stdout: bytes):
        self._stdout = stdout

    async def communicate(self):
        return self._stdout, b""


@pytest.mark.asyncio
async def test_find_pid_by_port_returns_first_pid_when_multiple(monkeypatch):
    guardian = AsyncProcessGuardian()

    async def _fake_shell(*args, **kwargs):
        return _FakeProc(b"1234\n5678\n")

    monkeypatch.setattr(
        "app.utils.process_guard.asyncio.create_subprocess_shell", _fake_shell
    )

    assert await guardian.find_pid_by_port(8080) == 1234


@pytest.mark.asyncio
async def test_find_pid_by_port_parses_single_pid(monkeypatch):
    guardian = AsyncProcessGuardian()

    async def _fake_shell(*args, **kwargs):
        return _FakeProc(b"4321\n")

    monkeypatch.setattr(
        "app.utils.process_guard.asyncio.create_subprocess_shell", _fake_shell
    )

    assert await guardian.find_pid_by_port(8081) == 4321


@pytest.mark.asyncio
async def test_watch_port_missing_required_fields_returns_instead_of_crashing():
    guardian = AsyncProcessGuardian()

    result = await asyncio.wait_for(guardian.watch_port({}), timeout=2)

    assert result is None


class _FakeConfigManager:
    def __init__(self):
        self.configs = {}
        self.save_calls = 0

    def save_configs(self):
        self.save_calls += 1


@pytest.mark.asyncio
async def test_watch_port_without_process_signature_skips_persistence(
    monkeypatch,
):
    guardian = AsyncProcessGuardian(check_interval=0.05, max_restart_attempts=1)
    manager = _FakeConfigManager()
    guardian.config_manager = manager

    async def _port_closed(port, host="127.0.0.1"):
        return False

    async def _no_pid(port):
        return None

    async def _restart_failed(*args, **kwargs):
        return False

    monkeypatch.setattr(guardian, "is_port_open", _port_closed)
    monkeypatch.setattr(guardian, "find_pid_by_port", _no_pid)
    monkeypatch.setattr(guardian, "restart_service", _restart_failed)

    config = {"name": "svc", "port": 9999, "restart_cmd": "run-service"}
    task = asyncio.create_task(guardian.watch_port(config))
    await asyncio.sleep(0.3)
    assert guardian.service_state["svc"]["state"] == "fused"
    task.cancel()
    # watch_port 捕获 CancelledError 后 break，任务正常结束；若缺键
    # KeyError 未被白名单捕获，协程会带异常提前结束，await 时会抛出。
    await task

    # 缺 process_signature：跳过持久化，不得写入伪造键
    assert manager.configs == {}
    assert manager.save_calls == 0
