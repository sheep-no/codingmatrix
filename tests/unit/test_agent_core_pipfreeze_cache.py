"""CodeValidator 构造时 `pip freeze` 结果在进程内只探测一次。

`validate_file` 工具每次调用都会新建 CodeValidator，原实现每次构造都跑
`pip freeze` 子进程，在生成循环里反复付出秒级开销。
"""
import subprocess

import pytest

from app.schema.codeRequest import AgentConfig
from app.utils.agent_core import CodeValidator, _cached_installed_packages


@pytest.fixture(autouse=True)
def _clear_cache():
    _cached_installed_packages.cache_clear()
    yield
    _cached_installed_packages.cache_clear()


def test_pip_freeze_spawned_once_per_process(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="flask==3.0.0\n", stderr="")

    monkeypatch.setattr("app.utils.agent_core.subprocess.run", fake_run)

    first = CodeValidator(tmp_path, AgentConfig())
    second = CodeValidator(tmp_path, AgentConfig())

    pip_calls = [c for c in calls if "pip" in c]
    assert len(pip_calls) == 1
    assert "flask" in first._installed_packages
    assert "flask" in second._installed_packages
