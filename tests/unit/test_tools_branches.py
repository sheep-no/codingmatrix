"""tools.py 分支补测：符号/导入提取、编辑工具、沙箱、命令、搜索、Git 与 SSRF。"""

import asyncio
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent import tools as tools_module
from app.agent.tools import (
    _execute_js_sandbox,
    _execute_python_sandbox,
    _extract_module_name,
    _run_git,
    _scan_dir,
    _tool_delete_files_by_pattern,
    _tool_execute_code,
    _tool_git_commit,
    _tool_git_diff,
    _tool_git_log,
    _tool_git_status,
    _tool_http_request,
    _tool_insert_content,
    _tool_list_files,
    _tool_partial_update,
    _tool_read_file,
    _tool_read_imports,
    _tool_read_symbols,
    _tool_regex_replace,
    _tool_run_command,
    _tool_search_files,
    _tool_summarize_file,
    _tool_web_search,
    _tool_write_file,
)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "main.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "\n"
        "class Service:\n"
        "    pass\n"
        "\n"
        "def helper(value):\n"
        "    return value\n",
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text(
        "const fs = require('fs');\n"
        "import { Router } from 'express';\n"
        "function init() { return 1; }\n"
        "class App {}\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "secret.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    return tmp_path


class TestReadTools:
    def test_read_oversized_file_is_rejected(self, project):
        big = project / "big.py"
        big.touch()
        os.truncate(big, 11 * 1024 * 1024)
        result = _tool_read_file(str(project), "big.py")
        assert "过大" in result["error"]

    def test_read_safe_join_error_is_returned(self, project):
        result = _tool_read_file(str(project), "../main.py")
        assert "越界" in result["error"]

    def test_list_rejects_file_path(self, project):
        result = _tool_list_files(str(project), "main.py")
        assert "不是目录" in result["error"]

    def test_scan_dir_skips_symlink(self, project, tmp_path):
        link = project / "link.py"
        link.symlink_to(tmp_path / "main.py")
        entries = []
        _scan_dir(project, entries, 0, 1, project)
        assert "link.py" not in [entry["path"] for entry in entries]

    def test_read_symbols_reports_missing_and_directory(self, project):
        assert "不存在" in _tool_read_symbols(str(project), "none.py")["error"]
        assert "不是文件" in _tool_read_symbols(str(project), "pkg")["error"]

    def test_read_imports_missing_file(self, project):
        assert "不存在" in _tool_read_imports(str(project), "none.py")["error"]

    def test_summarize_directory_and_unknown_language(self, project):
        assert "不是文件" in _tool_summarize_file(str(project), "pkg")["error"]
        (project / "notes.xyz").write_text("line\n", encoding="utf-8")
        summary = _tool_summarize_file(str(project), "notes.xyz")
        assert summary["language"] == "unknown"

    def test_extract_module_name_js_side_effect_import(self):
        assert _extract_module_name("import 'side-effect.css'", ".js") == "side-effect.css"

    def test_extract_module_name_unknown_extension_truncates(self):
        assert _extract_module_name("x" * 80, ".xyz") == "x" * 50

    def test_extract_module_name_require_go_rust_java(self):
        assert _extract_module_name("const fs = require('fs')", ".js") == "fs"
        assert _extract_module_name('import "fmt"', ".go") == "fmt"
        assert _extract_module_name("use std::io;", ".rs") == "std::io"
        assert _extract_module_name("import java.util.List;", ".java") == "java.util.List"

    def test_extract_module_name_falls_back_per_language(self):
        assert _extract_module_name("plain statement", ".go") == "plain statement"
        assert _extract_module_name("plain statement", ".py") == "plain statement"
        assert _extract_module_name("plain statement", ".rs") == "plain statement"
        assert _extract_module_name("plain statement", ".java") == "plain statement"
        assert _extract_module_name("const x = 1", ".js") == "const x = 1"

    def test_read_symbols_handles_nested_and_unclosed_parentheses(self, project):
        (project / "nested.py").write_text(
            "def outer(value=(1, 2)):\n"
            "    return value\n"
            "def broken(\n",
            encoding="utf-8",
        )
        result = _tool_read_symbols(str(project), "nested.py")
        names = [item["name"] for item in result["functions"]]
        assert names == ["outer", "broken"]

    def test_read_symbols_supports_go_and_rust(self, project):
        (project / "main.go").write_text("func Run() {\n}\n", encoding="utf-8")
        (project / "lib.rs").write_text("fn work() {\n}\n", encoding="utf-8")
        assert _tool_read_symbols(str(project), "main.go")["functions"][0]["name"] == "Run"
        assert _tool_read_symbols(str(project), "lib.rs")["functions"][0]["name"] == "work"

    def test_scan_dir_swallows_permission_errors(self, project, monkeypatch):
        def boom(self):
            raise PermissionError("denied")

        monkeypatch.setattr(Path, "iterdir", boom)
        entries = []
        _scan_dir(project, entries, 0, 2, project)
        assert entries == []

    def test_read_symbols_returns_error_on_read_failure(self, project, monkeypatch):
        monkeypatch.setattr(Path, "read_text", lambda self, **kw: (_ for _ in ()).throw(OSError("io")))
        assert "io" in _tool_read_symbols(str(project), "main.py")["error"]

    def test_read_imports_returns_error_on_read_failure(self, project, monkeypatch):
        monkeypatch.setattr(Path, "read_text", lambda self, **kw: (_ for _ in ()).throw(OSError("io")))
        assert "io" in _tool_read_imports(str(project), "main.py")["error"]

    def test_summarize_returns_error_on_failure(self, project, monkeypatch):
        monkeypatch.setattr(Path, "read_text", lambda self, **kw: (_ for _ in ()).throw(OSError("io")))
        assert "io" in _tool_summarize_file(str(project), "main.py")["error"]


class TestEditTools:
    def test_partial_update_function_with_braces(self, project):
        result = _tool_partial_update(
            str(project), "app.js", function_name="init", replacement="function init() { return 2; }"
        )
        assert result["success"] is True
        assert "return 2" in (project / "app.js").read_text(encoding="utf-8")

    def test_partial_update_indent_based_function(self, project):
        result = _tool_partial_update(
            str(project), "main.py", function_name="helper", replacement="def helper(value):\n    return value + 1"
        )
        assert result["success"] is True
        assert "value + 1" in (project / "main.py").read_text(encoding="utf-8")

    def test_partial_update_missing_function(self, project):
        result = _tool_partial_update(
            str(project), "main.py", function_name="nope", replacement="x"
        )
        assert result["success"] is False
        assert "未找到函数" in result["error"]

    def test_partial_update_unclosed_brace_block_is_reported_missing(self, project):
        (project / "broken.js").write_text("function init() {\n  return 1;\n", encoding="utf-8")
        result = _tool_partial_update(
            str(project), "broken.js", function_name="init", replacement="function init() {}"
        )
        assert result["success"] is False
        assert "未找到函数" in result["error"]

    def test_partial_update_nested_brace_block_matches_outer(self, project):
        (project / "nested.js").write_text(
            "function init() {\n"
            "  if (x) { return 1; }\n"
            "}\n"
            "const other = 2;\n",
            encoding="utf-8",
        )
        result = _tool_partial_update(
            str(project), "nested.js", function_name="init", replacement="function init() { return 9; }"
        )
        assert result["success"] is True
        updated = (project / "nested.js").read_text(encoding="utf-8")
        assert "return 9" in updated
        assert "const other = 2;" in updated

    def test_partial_update_indent_block_at_eof_replaces_tail(self, project):
        (project / "tail.py").write_text("def helper(a):\n    return a\n", encoding="utf-8")
        result = _tool_partial_update(
            str(project), "tail.py", function_name="helper", replacement="def helper(a):\n    return 0"
        )
        assert result["success"] is True
        assert result["size"] == len("def helper(a):\n    return 0\n")

    def test_partial_update_indent_block_stops_at_next_top_level(self, project):
        (project / "mod.py").write_text(
            "def helper(a):\n"
            "    # 注释保留在块内\n"
            "    return a\n"
            "\n"
            "VALUE = 1\n",
            encoding="utf-8",
        )
        result = _tool_partial_update(
            str(project), "mod.py", function_name="helper", replacement="def helper(a):\n    return a + 1"
        )
        assert result["success"] is True
        updated = (project / "mod.py").read_text(encoding="utf-8")
        assert "return a + 1" in updated
        assert "VALUE = 1" in updated

    def test_partial_update_catches_read_error(self, project, monkeypatch):
        original = Path.read_text

        def boom(self, *args, **kwargs):
            raise OSError("denied")

        monkeypatch.setattr(Path, "read_text", boom)
        result = _tool_partial_update(str(project), "main.py", target="x", replacement="y")
        monkeypatch.setattr(Path, "read_text", original)
        assert result["success"] is False
        assert "denied" in result["error"]

    def test_insert_without_line_or_anchor_appends(self, project):
        result = _tool_insert_content(str(project), "pkg/mod.py", "tail = 2")
        assert result["success"] is True
        assert (project / "pkg" / "mod.py").read_text(encoding="utf-8").endswith("tail = 2")

    def test_insert_negative_line_clamps(self, project):
        result = _tool_insert_content(str(project), "pkg/mod.py", "head = 0", line=-5)
        assert result["inserted_at_line"] == 1

    def test_insert_catches_write_error(self, project, monkeypatch):
        def boom(self, *args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(Path, "write_text", boom)
        result = _tool_insert_content(str(project), "pkg/mod.py", "x", line=1)
        assert result["success"] is False
        assert "disk full" in result["error"]

    def test_regex_replace_glob_mode(self, project):
        result = _tool_regex_replace(str(project), "**/*.py", r"x = 1", "x = 2", recursive=True)
        assert result["success"] is True
        assert "x = 2" in (project / "pkg" / "mod.py").read_text(encoding="utf-8")

    def test_regex_replace_rejects_traversal(self, tmp_path, project):
        outside = tmp_path / "outside.txt"
        outside.write_text("secret\n", encoding="utf-8")
        result = _tool_regex_replace(str(project / "pkg"), "../outside.txt", "secret", "pwn")
        assert result["success"] is False
        assert "越界" in result["error"]
        assert outside.read_text(encoding="utf-8") == "secret\n"

    def test_regex_replace_no_files_matched(self, project):
        result = _tool_regex_replace(str(project), "*.nope", "a", "b")
        assert result["success"] is False
        assert "未匹配到文件" in result["error"]

    def test_regex_replace_returns_error_on_read_failure(self, project, monkeypatch):
        monkeypatch.setattr(Path, "read_text", lambda self, **kw: (_ for _ in ()).throw(OSError("io")))
        result = _tool_regex_replace(str(project), "main.py", "a", "b")
        assert result["success"] is False
        assert "io" in result["error"]


class TestWriteTool:
    def test_placeholder_content_is_rejected(self, tmp_path):
        result = _tool_write_file(str(tmp_path), "a.py", "def x():\n    # 需替换为真实实现")
        assert result["success"] is False
        assert "占位符" in result["error"]

    def test_version_like_filename_is_rejected(self, tmp_path):
        result = _tool_write_file(str(tmp_path), "=1.2.3", "content")
        assert result["success"] is False
        assert "版本号" in result["error"]

    def test_syntax_warning_is_attached(self, tmp_path):
        result = _tool_write_file(str(tmp_path), "bad.py", "def broken(:\n")
        assert result["success"] is True
        assert "Python 语法错误" in result["warning"]

    def test_invalid_filename_is_rejected(self, tmp_path):
        result = _tool_write_file(str(tmp_path), "a<b>.py", "content")
        assert result["success"] is False
        assert "无效的文件名" in result["error"]

    def test_permission_error_is_returned(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "mkdir", lambda self, **kw: (_ for _ in ()).throw(PermissionError("denied")))
        result = _tool_write_file(str(tmp_path), "x.py", "print(1)")
        assert result["success"] is False
        assert "denied" in result["error"]

    def test_unexpected_error_is_returned(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "mkdir", lambda self, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        result = _tool_write_file(str(tmp_path), "x.py", "print(1)")
        assert result["success"] is False
        assert "boom" in result["error"]


class TestSyntaxChecks:
    def test_empty_vue_script_passes(self):
        assert tools_module._validate_file_syntax("empty.vue", "<template><div/></template>") == ""

    def test_python_syntax_inside_js_is_flagged(self):
        result = tools_module._validate_file_syntax("a.js", "def foo():\n    pass\n")
        assert "Python" in result

    def test_css_with_chinese_prose_is_flagged(self):
        content = "\n".join(["这是一个很长的中文描述文本内容用于测试检测逻辑"] * 5)
        result = tools_module._validate_file_syntax("a.css", content)
        assert "大量非代码文本" in result


class TestSandboxTools:
    def test_execute_code_disabled(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.ENABLE_CODE_SANDBOX", False, raising=False
        )
        result = _tool_execute_code("/tmp", "print(1)")
        assert result["success"] is False
        assert "已禁用" in result["error"]

    def test_execute_code_language_not_allowed(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.SANDBOX_LANGUAGES", "python", raising=False
        )
        result = _tool_execute_code("/tmp", "console.log(1)", language="ruby")
        assert result["success"] is False
        assert "不在沙箱允许列表" in result["error"]

    def test_execute_code_unknown_language_branch(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.SANDBOX_LANGUAGES",
            "python,javascript,typescript,ruby",
            raising=False,
        )
        result = _tool_execute_code("/tmp", "puts 1", language="ruby")
        assert result["success"] is False
        assert "不支持的语言" in result["error"]

    def test_execute_code_dispatches_python_and_js(self, monkeypatch):
        monkeypatch.setattr(tools_module, "_execute_python_sandbox", lambda code, timeout: {"success": True, "lang": "py"})
        monkeypatch.setattr(tools_module, "_execute_js_sandbox", lambda code, timeout: {"success": True, "lang": "js"})
        assert _tool_execute_code("/tmp", "print(1)")["lang"] == "py"
        assert _tool_execute_code("/tmp", "console.log(1)", language="javascript")["lang"] == "js"

    def test_execute_code_wraps_dispatch_errors(self, monkeypatch):
        def boom(code, timeout):
            raise RuntimeError("sandbox down")

        monkeypatch.setattr(tools_module, "_execute_python_sandbox", boom)
        result = _tool_execute_code("/tmp", "print(1)")
        assert result["success"] is False
        assert "sandbox down" in result["error"]

    def test_python_sandbox_rejects_dangerous_code(self):
        result = _execute_python_sandbox("import os\nos.getcwd()", timeout=5)
        assert result["success"] is False
        assert "安全限制" in result["error"]

    def test_python_sandbox_timeout(self, monkeypatch):
        def boom(*_args, **_kwargs):
            raise subprocess.TimeoutExpired(cmd="python3", timeout=1)

        monkeypatch.setattr(subprocess, "run", boom)
        result = _execute_python_sandbox("print(1)", timeout=1)
        assert "执行超时" in result["error"]

    def test_python_sandbox_unexpected_error(self, monkeypatch):
        def boom(*_args, **_kwargs):
            raise OSError("no python")

        monkeypatch.setattr(subprocess, "run", boom)
        result = _execute_python_sandbox("print(1)", timeout=1)
        assert result["success"] is False
        assert "no python" in result["error"]

    def test_python_sandbox_ignores_unlink_failure(self, monkeypatch):
        monkeypatch.setattr(os, "unlink", lambda _p: (_ for _ in ()).throw(OSError("busy")))
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
        )
        result = _execute_python_sandbox("print(1)", timeout=1)
        assert result["success"] is True

    def test_js_sandbox_rejects_dangerous_code(self):
        result = _execute_js_sandbox("require('fs').readFileSync('/etc/passwd')", timeout=5)
        assert result["success"] is False

    def test_js_sandbox_success_branch(self, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(returncode=0, stdout="ok\n", stderr=""),
        )
        result = _execute_js_sandbox("console.log('ok')", timeout=5)
        assert result["success"] is True
        assert result["output"] == "ok\n"

    def test_js_sandbox_failure_branch(self, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="boom"),
        )
        result = _execute_js_sandbox("console.log('ok')", timeout=5)
        assert result["success"] is False
        assert result["error"] == "boom"

    def test_js_sandbox_timeout(self, monkeypatch):
        def boom(*_args, **_kwargs):
            raise subprocess.TimeoutExpired(cmd="node", timeout=1)

        monkeypatch.setattr(subprocess, "run", boom)
        result = _execute_js_sandbox("console.log(1)", timeout=1)
        assert "执行超时" in result["error"]

    def test_js_sandbox_ignores_unlink_failure(self, monkeypatch):
        monkeypatch.setattr(os, "unlink", lambda _p: (_ for _ in ()).throw(OSError("busy")))
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
        )
        result = _execute_js_sandbox("console.log(1)", timeout=1)
        assert result["success"] is True

    def test_js_sandbox_unexpected_error(self, monkeypatch):
        def boom(*_args, **_kwargs):
            raise RuntimeError("node weird")

        monkeypatch.setattr(subprocess, "run", boom)
        result = _execute_js_sandbox("console.log(1)", timeout=1)
        assert result["success"] is False
        assert "node weird" in result["error"]


class TestRunCommand:
    @pytest.mark.parametrize("command", ["", "   ", None])
    def test_empty_command_rejected(self, project, command):
        result = _tool_run_command(str(project), command)
        assert result["success"] is False

    @pytest.mark.parametrize("command", [
        "rm -rf /",
        "shutdown now",
        "chmod 777 file",
        "sudo ls",
        "dd if=/dev/zero of=/dev/sda",
    ])
    def test_dangerous_commands_rejected(self, project, command):
        result = _tool_run_command(str(project), command)
        assert result["success"] is False
        assert "安全限制" in result["error"]

    def test_unbalanced_quotes_rejected(self, project):
        result = _tool_run_command(str(project), "python3 -c 'print(1)")
        assert result["success"] is False
        assert "解析失败" in result["error"]

    @pytest.mark.parametrize("command", ["sh -c id", "bash -l", "powershell -c id"])
    def test_shell_interpreters_rejected(self, project, command):
        result = _tool_run_command(str(project), command)
        assert result["success"] is False
        assert "Shell 解释器" in result["error"]

    def test_missing_workdir_rejected(self, project):
        result = _tool_run_command(str(project), "pwd", cwd="missing-dir")
        assert result["success"] is False
        assert "工作目录不存在" in result["error"]

    def test_successful_command_reports_metadata(self, project):
        result = _tool_run_command(str(project), "pwd")
        assert result["success"] is True
        assert result["return_code"] == 0
        assert result["cwd"] == str(project.resolve())

    def test_timeout_kills_process_group(self, project, monkeypatch):
        class FakeProc:
            pid = 4242
            returncode = -9

            def communicate(self, timeout=None):
                if timeout is not None:
                    raise subprocess.TimeoutExpired(cmd="python3", timeout=timeout)
                return None

            def kill(self):
                return None

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: FakeProc())
        monkeypatch.setattr(os, "killpg", lambda *a, **k: None)
        monkeypatch.setattr(os, "getpgid", lambda _pid: 4242)
        monkeypatch.setattr(subprocess, "signal", SimpleNamespace(SIGKILL=9), raising=False)
        result = _tool_run_command(str(project), "pwd", timeout=1)
        assert result["success"] is False
        assert "执行超时" in result["error"]

    def test_popen_failure_is_returned(self, project, monkeypatch):
        def boom(*_args, **_kwargs):
            raise OSError("spawn failed")

        monkeypatch.setattr(subprocess, "Popen", boom)
        result = _tool_run_command(str(project), "pwd")
        assert result["success"] is False
        assert "spawn failed" in result["error"]


class TestSearchFiles:
    def test_empty_pattern_rejected(self, project):
        assert "不能为空" in _tool_search_files(str(project), "  ")["error"]

    def test_missing_directory_rejected(self, project):
        assert "目录不存在" in _tool_search_files(str(project), "x", directory="nope")["error"]

    def test_search_finds_matches(self, project):
        result = _tool_search_files(str(project), "helper", file_pattern="*.py")
        assert result["success"] is True
        assert any(match["file"].endswith("main.py") for match in result["matches"])

    def test_search_timeout_is_reported(self, project, monkeypatch):
        def boom(*_args, **_kwargs):
            raise subprocess.TimeoutExpired(cmd="rg", timeout=15)

        monkeypatch.setattr(subprocess, "run", boom)
        result = _tool_search_files(str(project), "helper")
        assert result["success"] is False
        assert "搜索超时" in result["error"]

    def test_search_falls_back_to_grep(self, project, monkeypatch):
        calls = []
        real_run = subprocess.run

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ["rg", "--version"]:
                raise FileNotFoundError("rg")
            return real_run(cmd, **kwargs)

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = _tool_search_files(str(project), "helper", file_pattern="*.py")
        assert result["success"] is True
        assert any("grep" in str(cmd[0]) for cmd in calls)

    def test_search_skips_separator_lines_and_parses_context_numbers(self, project, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(
                returncode=0,
                stdout="--\nmain.py:12-ctx\nmain.py:x:weird\n",
                stderr="",
            ),
        )
        result = _tool_search_files(str(project), "x")
        assert result["matches"][0]["line_number"] == 12
        assert len(result["matches"]) == 1

    def test_search_wraps_unexpected_errors(self, project, monkeypatch):
        def boom(*_args, **_kwargs):
            raise RuntimeError("grep exploded")

        monkeypatch.setattr(subprocess, "run", boom)
        result = _tool_search_files(str(project), "x")
        assert result["success"] is False
        assert "grep exploded" in result["error"]

    def test_search_reports_error_status_without_matches(self, project, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr=""),
        )
        result = _tool_search_files(str(project), "x")
        assert result["matches"] == []
        assert result["total"] == 0


class TestGitTools:
    def test_run_git_success(self, project, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(returncode=0, stdout=" ok \n", stderr=""),
        )
        result = _run_git(str(project), ["status"])
        assert result == {"success": True, "stdout": "ok", "stderr": "", "return_code": 0}

    def test_run_git_timeout(self, project, monkeypatch):
        def boom(*_args, **_kwargs):
            raise subprocess.TimeoutExpired(cmd="git", timeout=1)

        monkeypatch.setattr(subprocess, "run", boom)
        assert "超时" in _run_git(str(project), ["status"])["error"]

    def test_run_git_missing_binary(self, project, monkeypatch):
        def boom(*_args, **_kwargs):
            raise FileNotFoundError("git")

        monkeypatch.setattr(subprocess, "run", boom)
        assert "未安装" in _run_git(str(project), ["status"])["error"]

    def test_run_git_unexpected_error(self, project, monkeypatch):
        def boom(*_args, **_kwargs):
            raise OSError("io")

        monkeypatch.setattr(subprocess, "run", boom)
        assert "io" in _run_git(str(project), ["status"])["error"]

    def test_git_status_parses_tracked_states(self, project, monkeypatch):
        def fake(_path, args):
            if args[:1] == ["status"]:
                return {"success": True, "stdout": "M  a.py\n?? b.py\nR  c.py\nD  d.py\nA  e.py\nC  f.py\nX  g.py"}
            return {"success": True, "stdout": "main"}

        monkeypatch.setattr(tools_module, "_run_git", fake)
        result = _tool_git_status(str(project))
        assert result["branch"] == "main"
        assert [item["status"] for item in result["files"]] == [
            "modified", "untracked", "renamed", "deleted", "added", "copied", "X",
        ]

    def test_git_status_propagates_failure_and_unknown_branch(self, project, monkeypatch):
        monkeypatch.setattr(
            tools_module,
            "_run_git",
            lambda _p, args: {"success": False, "error": "no repo"},
        )
        assert _tool_git_status(str(project))["error"] == "no repo"

        def fake(_p, args):
            if args[:1] == ["status"]:
                return {"success": True, "stdout": ""}
            return {"success": False}

        monkeypatch.setattr(tools_module, "_run_git", fake)
        assert _tool_git_status(str(project))["branch"] == "unknown"

    def test_git_diff_staged_and_detail_failure(self, project, monkeypatch):
        captured = []

        def fake(_p, args):
            captured.append(args)
            if "--stat" in args:
                return {"success": True, "stdout": "stat"}
            return {"success": False}

        monkeypatch.setattr(tools_module, "_run_git", fake)
        result = _tool_git_diff(str(project), file_path="a.py", staged=True)
        assert result["stat"] == "stat"
        assert result["diff"] == ""
        assert captured[0] == ["diff", "--cached", "--", "a.py", "--stat"]

    def test_git_diff_propagates_stat_failure(self, project, monkeypatch):
        monkeypatch.setattr(
            tools_module, "_run_git", lambda _p, args: {"success": False, "error": "bad"}
        )
        assert _tool_git_diff(str(project))["error"] == "bad"

    def test_git_commit_requires_message(self, project):
        assert "不能为空" in _tool_git_commit(str(project), "")["error"]

    def test_git_commit_with_files(self, project, monkeypatch):
        calls = []

        def fake(_p, args):
            calls.append(args)
            if args[:1] == ["commit"]:
                return {"success": True, "stdout": ""}
            return {"success": True, "stdout": "abc msg"}

        monkeypatch.setattr(tools_module, "_run_git", fake)
        result = _tool_git_commit(str(project), "msg", files=["a.py"])
        assert result["success"] is True
        assert ["add", "a.py"] in calls

    def test_git_commit_add_failure(self, project, monkeypatch):
        monkeypatch.setattr(
            tools_module,
            "_run_git",
            lambda _p, args: {"success": False, "stderr": "add failed"},
        )
        result = _tool_git_commit(str(project), "msg")
        assert result["success"] is False
        assert "add failed" in result["error"]

    def test_git_commit_nothing_to_commit(self, project, monkeypatch):
        def fake(_p, args):
            if args[:1] == ["add"]:
                return {"success": True}
            return {"success": False, "stderr": "nothing to commit, working tree clean"}

        monkeypatch.setattr(tools_module, "_run_git", fake)
        result = _tool_git_commit(str(project), "msg")
        assert result["nothing_to_commit"] is True

    def test_git_commit_other_failure(self, project, monkeypatch):
        def fake(_p, args):
            if args[:1] == ["add"]:
                return {"success": True}
            return {"success": False, "stderr": "hook failed"}

        monkeypatch.setattr(tools_module, "_run_git", fake)
        result = _tool_git_commit(str(project), "msg")
        assert result["success"] is False
        assert "hook failed" in result["error"]

    def test_git_log_parses_commits_and_filter(self, project, monkeypatch):
        captured = []

        def fake(_p, args):
            captured.append(args)
            return {
                "success": True,
                "stdout": "h1|s1|ann|2026-01-01|msg\nINVALID\n",
            }

        monkeypatch.setattr(tools_module, "_run_git", fake)
        result = _tool_git_log(str(project), count=2, file_path="a.py")
        assert result["total"] == 1
        assert result["commits"][0]["short_hash"] == "s1"
        assert captured[0][-2:] == ["--", "a.py"]

    def test_git_log_propagates_failure(self, project, monkeypatch):
        monkeypatch.setattr(
            tools_module, "_run_git", lambda _p, args: {"success": False, "error": "bad"}
        )
        assert _tool_git_log(str(project))["error"] == "bad"


class TestNetworkTools:
    def test_web_search_wraps_results(self, monkeypatch):
        class FakeSearch:
            async def search(self, query, count=5):
                return [
                    SimpleNamespace(title="T", url="https://x", snippet="S"),
                    SimpleNamespace(title="skip", url="", snippet=""),
                ]

        monkeypatch.setattr("app.utils.web_search.FreeWebSearch", FakeSearch)
        result = asyncio.run(_tool_web_search("/tmp", "q"))
        assert result["success"] is True
        assert result["results"] == ["T | https://x\nS"]

    def test_web_search_error_is_returned(self, monkeypatch):
        class FakeSearch:
            async def search(self, query, count=5):
                raise RuntimeError("offline")

        monkeypatch.setattr("app.utils.web_search.FreeWebSearch", FakeSearch)
        result = asyncio.run(_tool_web_search("/tmp", "q"))
        assert result["success"] is False
        assert "offline" in result["error"]

    @pytest.mark.parametrize("url, message", [
        ("", "缺少 url"),
        ("ftp://example.com", "仅支持 http/https"),
        ("http:///path", "缺少主机名"),
    ])
    def test_http_request_rejects_bad_urls(self, url, message):
        result = asyncio.run(_tool_http_request("/tmp", "GET", url))
        assert result["success"] is False
        assert message in result["error"]

    def test_http_request_dns_failure(self, monkeypatch):
        import socket

        def boom(*_args, **_kwargs):
            raise socket.gaierror("nxdomain")

        monkeypatch.setattr(socket, "getaddrinfo", boom)
        result = asyncio.run(_tool_http_request("/tmp", "GET", "https://nope.invalid"))
        assert result["success"] is False
        assert "DNS 解析失败" in result["error"]

    @pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "::1", "::ffff:127.0.0.1"])
    def test_http_request_blocks_internal_addresses(self, monkeypatch, address):
        import socket

        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *a, **k: [(socket.AF_INET6, None, None, None, (address, 0, 0, 0))],
        )
        result = asyncio.run(_tool_http_request("/tmp", "GET", "https://internal.example"))
        assert result["success"] is False
        assert "不允许访问" in result["error"]

    def test_http_request_success(self, monkeypatch):
        import socket

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def request(self, method, url, headers=None, json=None):
                return SimpleNamespace(status_code=200, headers={"h": "v"}, text="body")

        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *a, **k: [(socket.AF_INET, None, None, None, ("93.184.216.34", 0))],
        )
        monkeypatch.setattr("httpx.AsyncClient", FakeClient)
        result = asyncio.run(_tool_http_request("/tmp", "post", "https://example.com"))
        assert result["success"] is True
        assert result["status"] == 200
        assert result["body"] == "body"

    def test_http_request_invalid_ip_entry_is_skipped(self, monkeypatch):
        import socket

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def request(self, method, url, headers=None, json=None):
                return SimpleNamespace(status_code=204, headers={}, text="")

        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *a, **k: [(socket.AF_INET, None, None, None, ("not-an-ip", 0))],
        )
        monkeypatch.setattr("httpx.AsyncClient", FakeClient)
        result = asyncio.run(_tool_http_request("/tmp", "GET", "https://example.com"))
        assert result["success"] is True

    def test_http_request_wraps_exceptions(self, monkeypatch):
        import socket

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def request(self, *args, **kwargs):
                raise RuntimeError("network down")

        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *a, **k: [(socket.AF_INET, None, None, None, ("93.184.216.34", 0))],
        )
        monkeypatch.setattr("httpx.AsyncClient", FakeClient)
        result = asyncio.run(_tool_http_request("/tmp", "GET", "https://example.com"))
        assert result["success"] is False
        assert "network down" in result["error"]


class TestDeleteByPattern:
    def test_missing_directory(self, project):
        assert "目录不存在" in _tool_delete_files_by_pattern(str(project), "nope", "*.log")["error"]

    def test_no_matches(self, project):
        result = _tool_delete_files_by_pattern(str(project), ".", "*.log")
        assert result["deleted"] == 0

    def test_only_files_inside_project_are_deleted(self, project):
        inside = project / "a.log"
        inside.write_text("x", encoding="utf-8")
        outside = project.parent / "outside.log"
        outside.write_text("x", encoding="utf-8")
        result = _tool_delete_files_by_pattern(str(project), ".", "*.log")
        assert result["deleted"] == 1
        assert inside.exists() is False
        assert outside.exists() is True

    def test_remove_failure_is_collected(self, project, monkeypatch):
        (project / "a.log").write_text("x", encoding="utf-8")
        monkeypatch.setattr(os, "remove", lambda _p: (_ for _ in ()).throw(OSError("busy")))
        result = _tool_delete_files_by_pattern(str(project), ".", "*.log")
        assert result["deleted"] == 0
        assert "busy" in result["errors"][0]

    def test_outer_exception_is_returned(self, project, monkeypatch):
        def boom(*_args, **_kwargs):
            raise RuntimeError("glob failed")

        monkeypatch.setattr(tools_module.glob, "glob", boom)
        result = _tool_delete_files_by_pattern(str(project), ".", "*.log")
        assert result["success"] is False
        assert "glob failed" in result["error"]
