"""AsyncProcessGuardian.restart_service 回归测试。

PG2：restart_service 原先直接 `await proc.communicate()`，重启命令若在前台常驻
（如直接 `python app.py`）就永不返回，监控循环与熔断机制永久失效。修复后
「命令退出」与「端口就绪」并行等待，命令长时间不退出也会在 startup_timeout
内收敛。
"""
import asyncio
import socket
import sys
import time

import pytest

from app.utils.process_guard import AsyncProcessGuardian


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _foreground_server_cmd(port: int, seconds: int = 30) -> str:
    return (
        f"{sys.executable} -c "
        f"\"import socket,time; s=socket.socket(); "
        f"s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); "
        f"s.bind(('127.0.0.1', {port})); s.listen(); time.sleep({seconds})\""
    )


@pytest.fixture
def guardian():
    return AsyncProcessGuardian()


@pytest.mark.asyncio
async def test_foreground_restart_with_port_does_not_hang(guardian):
    port = _free_port()

    started = time.time()
    result = await asyncio.wait_for(
        guardian.restart_service(_foreground_server_cmd(port), port=port, startup_timeout=10),
        timeout=20,
    )
    elapsed = time.time() - started

    assert result is True
    assert elapsed < 10


@pytest.mark.asyncio
async def test_hanging_restart_without_open_port_fails_within_timeout(guardian):
    port = _free_port()

    started = time.time()
    result = await asyncio.wait_for(
        guardian.restart_service("sleep 60", port=port, startup_timeout=2),
        timeout=15,
    )
    elapsed = time.time() - started

    assert result is False
    assert elapsed < 10


@pytest.mark.asyncio
async def test_failing_restart_command_returns_false(guardian):
    result = await guardian.restart_service(
        "exit 7", port=_free_port(), startup_timeout=2
    )

    assert result is False


@pytest.mark.asyncio
async def test_restart_without_port_bounds_foreground_command(guardian):
    started = time.time()
    result = await asyncio.wait_for(
        guardian.restart_service("sleep 30", startup_timeout=1),
        timeout=10,
    )
    elapsed = time.time() - started

    assert result is True
    assert elapsed < 5


@pytest.mark.asyncio
async def test_restart_without_port_reports_command_failure(guardian):
    result = await guardian.restart_service("exit 3", startup_timeout=1)

    assert result is False
