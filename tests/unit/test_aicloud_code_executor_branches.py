"""CodeExecutor 分支覆盖：语言分发、AST 检查、超时、截断与 Go 流程。"""

import os
from types import SimpleNamespace

import pytest

from app.utils.aicloud import code_executor as module
from app.utils.aicloud.code_executor import (
    CodeExecutionResult,
    CodeExecutor,
    _find_banned_go_import,
)


class _Proc:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.killed = False

    async def communicate(self):
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True


@pytest.fixture
def executor(tmp_path):
    return CodeExecutor(workspace_path=str(tmp_path))


def test_default_workspace_created(tmp_path, monkeypatch):
    target = tmp_path / "aicloud_sandbox"
    monkeypatch.setattr(module.tempfile, "gettempdir", lambda: str(tmp_path))
    executor = CodeExecutor()
    assert executor.workspace_path == str(target)
    assert target.is_dir()


def test_sandbox_dirs_uses_parent(executor, tmp_path):
    dirs = executor._sandbox_dirs()
    assert dirs["WORK_DIR"] == str(tmp_path)
    assert dirs["HOME"] == str(tmp_path.parent)


def test_sandbox_dirs_root_falls_back(tmp_path, monkeypatch):
    executor = CodeExecutor(workspace_path="/")
    monkeypatch.setattr(module.os.path, "dirname", lambda _p: os.sep)
    dirs = executor._sandbox_dirs()
    assert dirs["HOME"] == dirs["WORK_DIR"]


def test_child_limits_cpu_and_address_space(executor, monkeypatch):
    calls = []
    fake_resource = SimpleNamespace(
        RLIMIT_CPU="cpu",
        RLIMIT_AS="as",
        setrlimit=lambda key, value: calls.append((key, value)),
    )
    monkeypatch.setitem(__import__("sys").modules, "resource", fake_resource)

    apply_fn = executor._child_limits(0, limit_address_space=True)
    apply_fn()
    assert calls[0] == ("cpu", (1, 1))
    assert calls[1][0] == "as"


def test_child_limits_without_address_space(executor, monkeypatch):
    calls = []
    fake_resource = SimpleNamespace(
        RLIMIT_CPU="cpu",
        RLIMIT_AS="as",
        setrlimit=lambda key, value: calls.append(key),
    )
    monkeypatch.setitem(__import__("sys").modules, "resource", fake_resource)
    executor._child_limits(3)()
    assert calls == ["cpu"]


def test_child_limits_swallow_errors(executor, monkeypatch):
    def boom(*_args):
        raise RuntimeError("no rlimit")

    fake_resource = SimpleNamespace(
        RLIMIT_CPU="cpu", RLIMIT_AS="as", setrlimit=boom
    )
    monkeypatch.setitem(__import__("sys").modules, "resource", fake_resource)
    executor._child_limits(1, limit_address_space=True)()


@pytest.mark.asyncio
async def test_execute_unsupported_language(executor):
    result = await executor.execute("x", "ruby")
    assert result.success is False
    assert "不支持的语言" in result.error
    assert result.exit_code == -1


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["python", "py", "PYTHON"])
async def test_execute_python_dispatch(executor, monkeypatch, language):
    async def fake_python(code, timeout):
        return CodeExecutionResult(True, code, "", 0, 0.0, "python")

    monkeypatch.setattr(executor, "_execute_python", fake_python)
    result = await executor.execute("code", language)
    assert result.language == "python"


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["javascript", "js", "node"])
async def test_execute_javascript_dispatch(executor, monkeypatch, language):
    async def fake_js(code, timeout):
        return CodeExecutionResult(True, code, "", 0, 0.0, "javascript")

    monkeypatch.setattr(executor, "_execute_javascript", fake_js)
    assert (await executor.execute("code", language)).language == "javascript"


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["go", "golang"])
async def test_execute_go_dispatch(executor, monkeypatch, language):
    async def fake_go(code, timeout):
        return CodeExecutionResult(True, code, "", 0, 0.0, "go")

    monkeypatch.setattr(executor, "_execute_go", fake_go)
    assert (await executor.execute("code", language)).language == "go"


@pytest.mark.asyncio
async def test_execute_python_syntax_error(executor):
    result = await executor._execute_python("def (:", 5)
    assert result.success is False
    assert "语法错误" in result.error


@pytest.mark.asyncio
async def test_execute_python_banned_import_value_error(executor):
    result = await executor._execute_python("import os", 5)
    assert result.success is False
    assert "禁止导入模块" in result.error


@pytest.mark.asyncio
async def test_execute_python_success(executor, monkeypatch, tmp_path):
    proc = _Proc(returncode=0, stdout=b"hi\n", stderr=b"")

    async def fake_exec(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_exec)
    result = await executor._execute_python("print('hi')", 5)
    assert result.success is True
    assert result.output == "hi\n"
    assert result.exit_code == 0
    assert not list(tmp_path.glob("exec_*.py"))


@pytest.mark.asyncio
async def test_execute_python_timeout(executor, monkeypatch):
    proc = _Proc(returncode=-9)

    async def fake_exec(*_args, **_kwargs):
        return proc

    async def timeout(_coro, timeout):
        raise module.asyncio.TimeoutError

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(module.asyncio, "wait_for", timeout)
    result = await executor._execute_python("print('hi')", 1)
    assert result.success is False
    assert "执行超时" in result.error
    assert proc.killed


@pytest.mark.asyncio
async def test_execute_python_nonzero_exit(executor, monkeypatch):
    proc = _Proc(returncode=2, stdout=b"", stderr=b"boom")

    async def fake_exec(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_exec)
    result = await executor._execute_python("raise SystemExit(2)", 5)
    assert result.success is False
    assert result.exit_code == -1
    assert result.error == "boom"


def test_check_python_ast_imports_and_names():
    executor = CodeExecutor(workspace_path="/tmp")
    import ast

    with pytest.raises(ValueError):
        executor._check_python_ast(ast.parse("import os"))
    with pytest.raises(ValueError):
        executor._check_python_ast(ast.parse("from pathlib import Path"))
    executor._check_python_ast(ast.parse("from . import sibling"))
    with pytest.raises(ValueError):
        executor._check_python_ast(ast.parse("__builtins__"))
    with pytest.raises(ValueError):
        executor._check_python_ast(ast.parse("().__class__.__subclasses__()"))
    with pytest.raises(ValueError):
        executor._check_python_ast(ast.parse("eval('1')"))
    with pytest.raises(ValueError):
        executor._check_python_ast(ast.parse("import x\nx.system('ls')"))

    executor._check_python_ast(ast.parse("print('ok')"))


@pytest.mark.asyncio
async def test_execute_javascript_forbidden_patterns(executor):
    result = await executor._execute_javascript("const fs = require('fs')", 5)
    assert result.success is False
    assert "require" in result.error


@pytest.mark.asyncio
async def test_execute_javascript_success_and_cleanup(executor, monkeypatch, tmp_path):
    proc = _Proc(returncode=0, stdout=b"out", stderr=b"")

    async def fake_exec(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_exec)
    result = await executor._execute_javascript("console.log(1)", 5)
    assert result.success is True
    assert result.output == "out"
    assert not list(tmp_path.glob("exec_*.js"))


@pytest.mark.asyncio
async def test_execute_javascript_timeout(executor, monkeypatch):
    proc = _Proc(returncode=-9)

    async def fake_exec(*_args, **_kwargs):
        return proc

    async def timeout(_coro, timeout):
        raise module.asyncio.TimeoutError

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(module.asyncio, "wait_for", timeout)
    result = await executor._execute_javascript("while(true){}", 1)
    assert result.success is False
    assert "执行超时" in result.error
    assert proc.killed


def test_find_banned_go_import_variants():
    assert _find_banned_go_import('import "os"') == "os"
    assert _find_banned_go_import('import _ "net/http"') == "net/http"
    assert _find_banned_go_import('import (\n  "fmt"\n  "os"\n)') == "os"
    assert _find_banned_go_import('import `unsafe`') == "unsafe"
    assert _find_banned_go_import('s := "os"') is None
    assert _find_banned_go_import('import "fmt"') is None


@pytest.mark.asyncio
async def test_execute_go_missing_main(executor):
    result = await executor._execute_go("package main", 5)
    assert result.success is False
    assert "func main()" in result.error


@pytest.mark.asyncio
async def test_execute_go_banned_import(executor):
    result = await executor._execute_go(
        "package main\nimport \"os\"\nfunc main() {}", 5
    )
    assert result.success is False
    assert "禁止导入包" in result.error


@pytest.mark.asyncio
async def test_execute_go_compile_failure(executor, monkeypatch, tmp_path):
    compile_proc = _Proc(returncode=1, stderr=b"compile error")

    async def fake_exec(*_args, **_kwargs):
        return compile_proc

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_exec)
    result = await executor._execute_go(
        "package main\nfunc main() {}", 5
    )
    assert result.success is False
    assert "compile error" in result.error
    assert result.exit_code == 1
    assert not list(tmp_path.glob("exec_*"))


@pytest.mark.asyncio
async def test_execute_go_success(executor, monkeypatch, tmp_path):
    compile_proc = _Proc(returncode=0)
    run_proc = _Proc(returncode=0, stdout=b"ok", stderr=b"")
    procs = iter([compile_proc, run_proc])

    async def fake_exec(*_args, **_kwargs):
        return next(procs)

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_exec)
    result = await executor._execute_go(
        "package main\nfunc main() { print(1) }", 5
    )
    assert result.success is True
    assert result.output == "ok"
    assert not list(tmp_path.glob("exec_*"))


@pytest.mark.asyncio
async def test_execute_go_run_timeout(executor, monkeypatch):
    compile_proc = _Proc(returncode=0)
    run_proc = _Proc(returncode=-9)
    procs = iter([compile_proc, run_proc])
    waits = {"n": 0}

    async def fake_exec(*_args, **_kwargs):
        return next(procs)

    async def wait_for(coro, timeout):
        waits["n"] += 1
        if waits["n"] == 1:
            return await coro
        raise module.asyncio.TimeoutError

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(module.asyncio, "wait_for", wait_for)
    result = await executor._execute_go(
        "package main\nfunc main() {}", 1
    )
    assert result.success is False
    assert "执行超时" in result.error
    assert run_proc.killed


@pytest.mark.asyncio
async def test_execute_go_missing_package_main_is_prepended(executor, monkeypatch):
    compile_proc = _Proc(returncode=1, stderr=b"nope")
    captured = {}

    async def fake_exec(*args, **_kwargs):
        with open(args[-1], encoding="utf-8") as handle:
            captured["source"] = handle.read()
        return compile_proc

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_exec)
    await executor._execute_go("func main() {}", 5)
    assert captured["source"].startswith("package main\n")


def test_truncate_output(executor):
    assert executor._truncate_output("short") == "short"
    long_text = "x" * (executor.MAX_OUTPUT_SIZE + 5)
    result = executor._truncate_output(long_text)
    assert result.endswith("... (输出已截断)")
    assert len(result) < len(long_text) + 20
