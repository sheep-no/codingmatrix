"""TFC1 回归：非 Python 项目按框架预设安装依赖。

此前 ``_install_dependencies`` 只在 Python venv 分支被调用，JS/Go/Java/Rust/CPP
项目的 ``setup_commands``（npm install / go mod download / ...）全库零消费，
非 Python 项目在无依赖状态下执行测试必然失败。
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.agent.test_runner import IsolatedTestRunner, TestResult


class _FakeProc:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode
        self.pid = 4242

    async def communicate(self):
        return b"", b""

    async def wait(self):
        return self.returncode

    def kill(self):
        pass


@pytest.fixture
def runner(tmp_path):
    r = IsolatedTestRunner(project_path=tmp_path, enable_security_scan=False)
    r._work_dir = tmp_path
    return r


@pytest.mark.asyncio
async def test_setup_commands_are_executed_in_work_dir(runner, monkeypatch):
    runner._detected_config = SimpleNamespace(
        language="javascript",
        framework="jest",
        setup_commands=["npm install"],
    )
    recorded = []

    async def fake_shell(command, **kwargs):
        recorded.append((command, kwargs.get("cwd"), kwargs.get("preexec_fn")))
        return _FakeProc(0)

    monkeypatch.setattr(asyncio, "create_subprocess_shell", fake_shell)

    assert await runner._install_dependencies_for_config() is True
    assert len(recorded) == 1
    command, cwd, preexec_fn = recorded[0]
    assert command == "npm install"
    assert cwd == str(runner._work_dir)


@pytest.mark.asyncio
async def test_no_setup_commands_short_circuits(runner, monkeypatch):
    runner._detected_config = SimpleNamespace(
        language="go",
        framework="go_test",
        setup_commands=[],
    )
    called = []

    async def fake_shell(*args, **kwargs):
        called.append(args)
        return _FakeProc(0)

    monkeypatch.setattr(asyncio, "create_subprocess_shell", fake_shell)

    assert await runner._install_dependencies_for_config() is True
    assert called == []


@pytest.mark.asyncio
async def test_failed_setup_command_reported_without_raising(runner, monkeypatch):
    runner._detected_config = SimpleNamespace(
        language="java",
        framework="maven",
        setup_commands=["mvn dependency:resolve"],
    )

    async def fake_shell(command, **kwargs):
        return _FakeProc(1)

    monkeypatch.setattr(asyncio, "create_subprocess_shell", fake_shell)

    assert await runner._install_dependencies_for_config() is False


@pytest.mark.asyncio
async def test_missing_detected_config_is_tolerated(runner, monkeypatch):
    runner._detected_config = None

    async def fake_shell(*args, **kwargs):  # pragma: no cover - 不应被调用
        raise AssertionError("无配置时不应启动子进程")

    monkeypatch.setattr(asyncio, "create_subprocess_shell", fake_shell)

    assert await runner._install_dependencies_for_config() is True


@pytest.mark.asyncio
async def test_timeout_marks_failure(runner, monkeypatch):
    runner._detected_config = SimpleNamespace(
        language="rust",
        framework="cargo",
        setup_commands=["cargo build"],
    )

    class _HangingProc(_FakeProc):
        async def communicate(self):
            await asyncio.sleep(3600)

    async def fake_shell(command, **kwargs):
        return _HangingProc()

    monkeypatch.setattr(asyncio, "create_subprocess_shell", fake_shell)
    monkeypatch.setattr("app.agent.test_runner.DEPENDENCY_SETUP_TIMEOUT", 0.01)

    assert await runner._install_dependencies_for_config() is False


@pytest.mark.asyncio
async def test_run_tests_invokes_install_for_non_python(tmp_path, monkeypatch):
    (tmp_path / "go.mod").write_text("module example\n\ngo 1.22\n")
    runner = IsolatedTestRunner(project_path=tmp_path, enable_security_scan=False)
    runner._framework_detector = SimpleNamespace(
        detect=lambda _p: SimpleNamespace(
            language="go",
            framework="go_test",
            test_command="go test ./... -v",
            output_format="go_json",
            setup_commands=["go mod download"],
        )
    )
    install_calls = []

    async def fake_install():
        install_calls.append(1)
        return True

    async def fake_execute(_cmd):
        return TestResult(
            success=True, total_tests=1, passed=1, failed=0,
            errors=0, logs="ok", failed_tests=[],
            language="go", framework="go_test",
        )

    async def noop_async(*_args, **_kwargs):
        return None

    monkeypatch.setattr(runner, "_install_dependencies_for_config", fake_install)
    monkeypatch.setattr(runner, "_execute_test", fake_execute)
    monkeypatch.setattr(runner, "_start_service_containers", noop_async)
    monkeypatch.setattr(runner, "_cleanup_service_containers", noop_async)

    result = await runner.run_tests(test_command="go test ./... -v")

    assert install_calls == [1]
    assert result.language == "go"
