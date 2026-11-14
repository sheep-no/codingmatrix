"""code_execution 节点校验、语言分派与子进程边界补测。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils.workflow.node_types.code_execution import CodeExecutionNode


def _node(**params):
    return CodeExecutionNode("node-1", params)


@pytest.mark.parametrize("params,fragment", [
    ({"code": 123}, "must be a string"),
    ({"code": "   "}, "cannot be empty"),
    ({"code": "x", "timeout": "10"}, "must be a number"),
    ({"code": "x", "timeout": 0}, "between 1 and 300"),
])
def test_validate_params_rejections(params, fragment):
    errors = _node(**params).validate_params()
    assert any(fragment in error for error in errors)


def test_validate_params_accepts_js_language():
    assert _node(code="x", language="js", timeout=1.5).validate_params() == []


def test_optional_params_defaults():
    params = _node(code="x").get_optional_params()
    assert params == {"language": "python", "timeout": 60}


async def test_execute_rejects_unsupported_language():
    result = await _node(code="x", language="ruby").execute({})
    assert result.success is False
    assert "Unsupported language" in result.error


async def test_execute_javascript_dispatch(monkeypatch):
    node = _node(code="console.log(1)", language="js")
    monkeypatch.setattr(
        node, "_execute_javascript",
        AsyncMock(return_value={"stdout": "1", "stderr": "", "exit_code": 0}),
    )

    result = await node.execute({})

    assert result.success is True
    assert result.data["language"] == "js"


async def test_execute_nonzero_exit_includes_stderr(monkeypatch):
    node = _node(code="x")
    monkeypatch.setattr(
        node, "_execute_python",
        AsyncMock(return_value={"stdout": "", "stderr": "  boom\n", "exit_code": 2}),
    )

    result = await node.execute({})

    assert result.success is False
    assert "exit code 2" in result.error
    assert "boom" in result.error


async def test_execute_nonzero_exit_without_stderr(monkeypatch):
    node = _node(code="x")
    monkeypatch.setattr(
        node, "_execute_python",
        AsyncMock(return_value={"stdout": "", "stderr": "", "exit_code": 2}),
    )

    result = await node.execute({})

    assert result.error == "Code execution failed with exit code 2"


async def test_execute_timeout_branch(monkeypatch):
    node = _node(code="x", timeout=1)
    monkeypatch.setattr(node, "_execute_python", AsyncMock(side_effect=asyncio.TimeoutError))

    result = await node.execute({})

    assert result.success is False
    assert "timeout" in result.error
    assert result.metadata["timeout"] == 1


async def test_execute_generic_exception(monkeypatch):
    node = _node(code="x")
    monkeypatch.setattr(node, "_execute_python", AsyncMock(side_effect=OSError("spawn failed")))

    result = await node.execute({})

    assert result.success is False
    assert "spawn failed" in result.error


@pytest.mark.parametrize("language,suffix,command", [
    ("python", ".py", "python3"),
    ("javascript", ".js", "node"),
])
async def test_execute_writes_temp_file_and_cleans_up(
    monkeypatch, tmp_path, language, suffix, command
):
    node = _node(code="payload", language=language)
    captured = {}

    async def fake_run(cmd, timeout):
        captured["cmd"] = cmd
        captured["exists"] = __import__("os").path.exists(cmd[1])
        captured["content"] = __import__("pathlib").Path(cmd[1]).read_text()
        return {"stdout": "", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(node, "_run_command", fake_run)

    result = await node.execute({})

    assert result.success is True
    assert captured["cmd"][0] == command
    assert captured["cmd"][1].endswith(suffix)
    assert captured["exists"] is True
    assert captured["content"] == "payload"


async def test_run_command_kills_process_group_on_timeout(monkeypatch):
    node = _node(code="x")
    process = MagicMock()
    process.pid = 123
    process.returncode = -9
    process.wait = AsyncMock()

    async def fake_exec(*args, **kwargs):
        return process

    async def fake_gather(*args, **kwargs):
        for arg in args:
            if asyncio.iscoroutine(arg):
                arg.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(asyncio, "gather", fake_gather)
    killed = []
    monkeypatch.setattr("os.killpg", lambda pgid, sig: killed.append(pgid))
    monkeypatch.setattr("os.getpgid", lambda pid: 456)

    with pytest.raises(asyncio.TimeoutError):
        await node._run_command(["python3", "x.py"], 1)

    assert killed == [456]
    process.wait.assert_awaited_once()


async def test_run_command_falls_back_to_process_kill(monkeypatch):
    node = _node(code="x")
    process = MagicMock()
    process.pid = 123
    process.wait = AsyncMock()
    process.kill = MagicMock()

    async def fake_exec(*args, **kwargs):
        return process

    async def fake_gather(*args, **kwargs):
        for arg in args:
            if asyncio.iscoroutine(arg):
                arg.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(asyncio, "gather", fake_gather)

    def fake_killpg(pgid, sig):
        raise ProcessLookupError

    monkeypatch.setattr("os.killpg", fake_killpg)
    monkeypatch.setattr("os.getpgid", lambda pid: 456)

    with pytest.raises(asyncio.TimeoutError):
        await node._run_command(["python3", "x.py"], 1)

    process.kill.assert_called_once()


async def test_read_limited_none_stream():
    assert await CodeExecutionNode._read_limited(None, 10) == b""


async def test_read_limited_truncates_to_limit():
    calls = []

    class Stream:
        def __init__(self):
            self.chunks = [b"0123456789", b"abcdefghij", b""]

        async def read(self, size):
            calls.append(size)
            return self.chunks.pop(0)

    result = await CodeExecutionNode._read_limited(Stream(), 12)
    assert result == b"0123456789ab"
    assert calls == [8192, 8192, 8192]


async def test_read_limited_skips_chunks_past_limit():
    class Stream:
        def __init__(self):
            self.chunks = [b"0123456789", b"abc", b""]

        async def read(self, size):
            return self.chunks.pop(0)

    result = await CodeExecutionNode._read_limited(Stream(), 5)
    assert result == b"01234"
