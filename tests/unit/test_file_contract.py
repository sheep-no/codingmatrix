"""
文件契约与审查数据模型单元测试

覆盖：
- FileContract 路径验证、内容验证
- ReviewResult / TaskStep Pydantic 模型
- _degrade_step 降级步骤构造
"""

import os
import tempfile
import pytest
from pathlib import Path

from app.agent.file_contract import (
    FileContract,
    ReviewResult,
    TaskStep,
    _degrade_step,
)


class TestFileContractPathValidation:
    def test_valid_relative_path(self):
        fc = FileContract(operation="read", file_path="src/main.py")
        assert fc.validate_path() is True

    def test_protected_path_etc(self):
        fc = FileContract(operation="read", file_path="/etc/passwd")
        assert fc.validate_path() is False

    def test_protected_path_root(self):
        fc = FileContract(operation="read", file_path="/root/.ssh/id_rsa")
        assert fc.validate_path() is False

    def test_protected_path_proc(self):
        fc = FileContract(operation="read", file_path="/proc/1/status")
        assert fc.validate_path() is False

    def test_protected_file_git_config(self):
        fc = FileContract(operation="read", file_path="/some/path/.git/config")
        assert fc.validate_path() is False

    def test_protected_file_ssh_keys(self):
        fc = FileContract(operation="read", file_path="/home/user/.ssh/id_rsa")
        assert fc.validate_path() is False

    def test_base_path_constraint_valid(self):
        # /tmp is protected, so use /home-like path via monkeypatching
        fc = FileContract(
            operation="read",
            file_path="/home/user/project/test.py",
            base_path="/home/user/project",
        )
        # Patch Path.resolve to return consistent values
        from unittest.mock import patch as _patch
        import pathlib
        with _patch.object(pathlib.Path, "resolve", return_value=pathlib.Path("/home/user/project/test.py")):
            assert fc.validate_path() is True

    def test_base_path_constraint_violated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "project")
            os.makedirs(project_dir)
            fc = FileContract(
                operation="read",
                file_path="/etc/passwd",
                base_path=project_dir,
            )
            assert fc.validate_path() is False

    def test_disallowed_extension(self):
        fc = FileContract(operation="read", file_path="malware.exe")
        assert fc.validate_path() is False

    def test_allowed_extensions(self):
        for ext in [".py", ".js", ".ts", ".vue", ".html", ".css", ".md", ".json", ".yaml", ".sh"]:
            fc = FileContract(operation="read", file_path=f"file{ext}")
            assert fc.validate_path() is True, f"Extension {ext} should be allowed"

    def test_no_extension_passes(self):
        fc = FileContract(operation="read", file_path="Makefile")
        # no extension → empty suffix → not in allowed list → False
        # Actually the code checks `if ext and ext not in ...` so empty ext passes
        assert fc.validate_path() is True

    def test_validate_path_exception_handling(self):
        fc = FileContract(operation="read", file_path="")
        # should not raise, returns bool
        result = fc.validate_path()
        assert isinstance(result, bool)


class TestFileContractContentValidation:
    def test_safe_content(self):
        fc = FileContract(operation="write", file_path="test.py")
        assert fc.validate_content("def hello():\n    print('hello')") is True

    def test_oversized_content(self):
        fc = FileContract(operation="write", file_path="test.py", max_size=100)
        assert fc.validate_content("x" * 200) is False

    def test_dangerous_rm_rf(self):
        fc = FileContract(operation="write", file_path="test.py")
        assert fc.validate_content('os.system("rm -rf /")') is False

    def test_dangerous_eval(self):
        fc = FileContract(operation="write", file_path="test.py")
        assert fc.validate_content('eval("malicious code")') is False

    def test_dangerous_exec(self):
        fc = FileContract(operation="write", file_path="test.py")
        assert fc.validate_content('exec("import os")') is False

    def test_dangerous_subprocess_shell(self):
        fc = FileContract(operation="write", file_path="test.py")
        assert fc.validate_content('subprocess.run("ls", shell=True)') is False

    def test_dangerous_import_ctypes(self):
        fc = FileContract(operation="write", file_path="test.py")
        # The regex `import\s+ctypes\s` requires trailing space; test with context
        assert fc.validate_content("import ctypes\nfrom ctypes import c_int") is False

    def test_dangerous_import_os_subprocess(self):
        fc = FileContract(operation="write", file_path="test.py")
        assert fc.validate_content('__import__("os")') is False

    def test_dangerous_os_system(self):
        fc = FileContract(operation="write", file_path="test.py")
        assert fc.validate_content("os.system('ls')") is False

    def test_dangerous_os_popen(self):
        fc = FileContract(operation="write", file_path="test.py")
        assert fc.validate_content("os.popen('ls')") is False

    def test_safe_code_patterns(self):
        fc = FileContract(operation="write", file_path="test.py")
        safe = """
import os
from pathlib import Path

def process():
    result = subprocess.run(["ls"], capture_output=True)
    return result.stdout
"""
        assert fc.validate_content(safe) is True

    def test_default_max_size(self):
        fc = FileContract(operation="write", file_path="test.py")
        assert fc.max_size == 1024 * 1024


class TestFileContractDefaults:
    def test_default_extensions(self):
        fc = FileContract(operation="read", file_path="test.py")
        assert ".py" in fc.allowed_extensions
        assert ".js" in fc.allowed_extensions
        assert ".ts" in fc.allowed_extensions

    def test_require_backup_default(self):
        fc = FileContract(operation="write", file_path="test.py")
        assert fc.require_backup is True

    def test_base_path_default_none(self):
        fc = FileContract(operation="read", file_path="test.py")
        assert fc.base_path is None


class TestReviewResult:
    def test_approved(self):
        r = ReviewResult(approved=True)
        assert r.approved is True
        assert r.issues == []
        assert r.suggestions == []
        assert r.risk_level == "low"

    def test_rejected_with_issues(self):
        r = ReviewResult(
            approved=False,
            issues=["missing tests", "no error handling"],
            suggestions=["add pytest"],
            risk_level="high",
        )
        assert r.approved is False
        assert len(r.issues) == 2
        assert r.risk_level == "high"

    def test_invalid_risk_level(self):
        with pytest.raises(Exception):
            ReviewResult(approved=True, risk_level="critical")


class TestTaskStep:
    def test_file_operation_step(self):
        step = TaskStep(
            type="file_operation",
            description="Read main.py",
            params={"operation": "read", "path": "main.py"},
        )
        assert step.type == "file_operation"
        assert step.degraded is False

    def test_code_generation_step(self):
        step = TaskStep(
            type="code_generation",
            description="Generate auth module",
        )
        assert step.type == "code_generation"
        assert step.params == {}

    def test_ai_call_step(self):
        step = TaskStep(
            type="ai_call",
            description="Analyze code",
            params={"task": "find bugs"},
        )
        assert step.type == "ai_call"

    def test_tool_call_step(self):
        step = TaskStep(
            type="tool_call",
            description="Run linter",
        )
        assert step.type == "tool_call"

    def test_degraded_flag(self):
        step = TaskStep(
            type="ai_call",
            description="fallback",
            degraded=True,
        )
        assert step.degraded is True

    def test_invalid_type_raises(self):
        with pytest.raises(Exception):
            TaskStep(type="invalid", description="bad")


class TestDegradeStep:
    def test_basic_degrade(self):
        step = _degrade_step("build a website", "parsing failed")
        assert step["type"] == "ai_call"
        assert "parsing failed" in step["description"]
        assert step["params"]["task"] == "build a website"
        assert step["degraded"] is True

    def test_degrade_with_schema_error(self):
        step = _degrade_step("task", "schema error: field missing")
        assert "schema error" in step["description"]
