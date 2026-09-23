"""test_runner 缺陷回归：TR3 / TR5 / TR6 / TR8。"""

import shutil
import tempfile
from pathlib import Path

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
