"""test_runner 缺陷回归：TR3 / TR5 / TR6 / TR8 / 清理阻塞。"""

import asyncio
import shutil
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent import test_runner as tr
from app.agent.test_runner import IsolatedTestRunner, TestResult


class TestSuccessReconciledWithParsedFailures:
    """TR3: returncode=0 但日志含失败时不能判定成功"""

    def _make_runner(self, project: Path) -> IsolatedTestRunner:
        return IsolatedTestRunner(project_path=project, enable_security_scan=False)

    def test_zero_exit_with_parsed_failures_flips_success(self, tmp_path):
        runner = self._make_runner(tmp_path)
        result = TestResult(
            success=True, total_tests=0, passed=0, failed=0,
            errors=0, logs="3 passed, 1 failed in 0.5s",
            failed_tests=[],
        )

        parsed = runner._parse_with_output_parser(result)

        assert parsed.failed == 1
        assert parsed.success is False

    def test_zero_exit_without_failures_stays_success(self, tmp_path):
        runner = self._make_runner(tmp_path)
        result = TestResult(
            success=True, total_tests=0, passed=0, failed=0,
            errors=0, logs="3 passed in 0.5s",
            failed_tests=[],
        )

        parsed = runner._parse_with_output_parser(result)

        assert parsed.failed == 0
        assert parsed.success is True


class TestSecurityScanCoversAllFiles:
    """TR5: 安全扫描不能静默截断前 100 个文件"""

    def test_all_python_files_are_scanned(self):
        project = Path(tempfile.mkdtemp(prefix="test_scan_all_"))
        try:
            for i in range(150):
                (project / f"mod_{i:03d}.py").write_text(
                    "import os\nos.system('echo hi')\n"
                )

            warnings = IsolatedTestRunner(
                project_path=project, enable_security_scan=True
            )._scan_security()

            assert len(warnings) == 150
        finally:
            shutil.rmtree(str(project), ignore_errors=True)


class TestRequirementFilteringIsVisible:
    """TR6: 白名单外依赖被剔除时必须记录日志"""

    def test_dropped_dependencies_are_logged(self, tmp_path, monkeypatch):
        req = tmp_path / "requirements.txt"
        req.write_text("requests==2.31.0\nboto3==1.34.0\n")
        output = tmp_path / "filtered.txt"

        warnings = []
        monkeypatch.setattr(tr.logger, "warning", lambda *a, **k: warnings.append(a))
        runner = IsolatedTestRunner(project_path=tmp_path, enable_security_scan=False)

        ok = runner._filter_requirements(req, output)

        assert ok is True
        assert "requests==2.31.0" in output.read_text()
        assert "boto3" not in output.read_text()
        assert any("boto3" in str(w) for w in warnings)

    def test_no_dropped_dependencies_does_not_warn(self, tmp_path, monkeypatch):
        req = tmp_path / "requirements.txt"
        req.write_text("requests==2.31.0\n")
        output = tmp_path / "filtered.txt"

        warnings = []
        monkeypatch.setattr(tr.logger, "warning", lambda *a, **k: warnings.append(a))
        runner = IsolatedTestRunner(project_path=tmp_path, enable_security_scan=False)

        runner._filter_requirements(req, output)

        assert warnings == []


class TestCleanupBoundary:
    """TR8: 清理不得触碰用户原始项目目录"""

    async def test_cleanup_does_not_delete_user_pycache(self):
        project = Path(tempfile.mkdtemp(prefix="test_cleanup_"))
        try:
            pycache = project / "__pycache__"
            pycache.mkdir()
            (pycache / "mod.cpython-311.pyc").write_bytes(b"x")

            runner = IsolatedTestRunner(project_path=project, enable_security_scan=False)
            await runner._cleanup()

            assert pycache.exists()
        finally:
            shutil.rmtree(str(project), ignore_errors=True)


class TestCleanupRunsOffEventLoop:
    """沙箱回收（rmtree 遍历删除大量文件）不得在事件循环线程执行"""

    async def test_cleanup_rmtree_runs_in_worker_thread(self, monkeypatch):
        project = Path(tempfile.mkdtemp(prefix="test_cleanup_worker_"))
        sandbox = project / "sandbox"
        sandbox.mkdir()
        (sandbox / "f.txt").write_text("x")

        runner = IsolatedTestRunner(project_path=project, enable_security_scan=False)
        runner._temp_dir = sandbox

        loop_thread = threading.get_ident()
        seen_threads = []
        real_rmtree = tr.shutil.rmtree

        def spy_rmtree(*args, **kwargs):
            seen_threads.append(threading.get_ident())
            return real_rmtree(*args, **kwargs)

        monkeypatch.setattr(tr.shutil, "rmtree", spy_rmtree)
        monkeypatch.setattr(tr.asyncio, "sleep", _noop_sleep)
        try:
            await runner._cleanup()
        finally:
            real_rmtree(str(project), ignore_errors=True)

        assert seen_threads, "shutil.rmtree 应被调用"
        assert loop_thread not in seen_threads, "rmtree 不得在事件循环线程执行"
        assert not sandbox.exists()

    async def test_run_tests_fallback_rmtree_runs_in_worker_thread(
        self, tmp_path, monkeypatch
    ):
        runner = IsolatedTestRunner(project_path=tmp_path, enable_security_scan=False)
        sandbox = Path(tempfile.mkdtemp(prefix="test_run_tests_worker_"))
        (sandbox / "f.txt").write_text("x")

        async def _noop_async(*_args, **_kwargs):
            return None

        async def _fake_create_venv():
            runner._temp_dir = sandbox
            runner._venv_dir = sandbox / "venv"
            runner._work_dir = sandbox / "project"
            runner._work_dir.mkdir()
            runner._venv_python = "/usr/bin/python3"

        async def _fake_build_command(*_args, **_kwargs):
            return ["pytest", "-q"]

        async def _fake_execute_test(_cmd):
            return TestResult(
                success=True, total_tests=1, passed=1, failed=0,
                errors=0, logs="1 passed", failed_tests=[],
            )

        async def _fake_install_dependencies():
            return True

        runner._framework_detector = SimpleNamespace(
            detect=lambda _p: SimpleNamespace(language="python", framework="pytest")
        )
        monkeypatch.setattr(runner, "_scan_security", lambda: [])
        monkeypatch.setattr(runner, "_start_service_containers", _noop_async)
        monkeypatch.setattr(runner, "_cleanup_service_containers", _noop_async)
        monkeypatch.setattr(runner, "_cleanup", _noop_async)
        monkeypatch.setattr(runner, "_create_venv", _fake_create_venv)
        monkeypatch.setattr(runner, "_copy_project", _noop_async)
        monkeypatch.setattr(runner, "_install_dependencies", _fake_install_dependencies)
        monkeypatch.setattr(runner, "_build_test_command", _fake_build_command)
        monkeypatch.setattr(runner, "_execute_test", _fake_execute_test)
        monkeypatch.setattr(
            runner, "_parse_with_output_parser", lambda result: result
        )

        loop_thread = threading.get_ident()
        seen_threads = []
        real_rmtree = tr.shutil.rmtree

        def spy_rmtree(*args, **kwargs):
            seen_threads.append(threading.get_ident())
            return real_rmtree(*args, **kwargs)

        monkeypatch.setattr(tr, "_get_semaphore", lambda: asyncio.Semaphore(1))
        monkeypatch.setattr(tr.tempfile, "mkdtemp", lambda prefix="": str(sandbox))
        monkeypatch.setattr(tr.shutil, "rmtree", spy_rmtree)
        try:
            await runner.run_tests(test_paths=["tests"])
        finally:
            real_rmtree(str(sandbox), ignore_errors=True)

        assert seen_threads, "兜底 rmtree 应被调用"
        assert loop_thread not in seen_threads, "兜底 rmtree 不得在事件循环线程执行"
        assert not sandbox.exists()


async def _noop_sleep(*_args, **_kwargs):
    return None
