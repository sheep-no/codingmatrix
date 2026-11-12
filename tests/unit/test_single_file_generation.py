import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.api.v1.ai_agent import single_file_generation as module


def test_infer_single_file_request_from_simple_python_prompt():
    result = module.infer_single_file_request("写一个输出 helloworld 的 Python 文件")

    assert result == {
        "language": "python",
        "extension": ".py",
        "filename": "helloworld.py",
    }


def test_project_request_keeps_full_orchestration_path():
    assert module.infer_single_file_request("创建一个 FastAPI 项目") is None


@pytest.mark.asyncio
async def test_generate_single_file_validates_and_runs_in_temp_dir(monkeypatch, tmp_path):
    async def fake_call_llm(**_kwargs):
        return {
            "choices": [{"message": {"content": 'print("helloworld")'}}],
        }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "call_llm", fake_call_llm)

    result = await module.generate_single_file("写一个输出 helloworld 的 Python 文件")

    file_path = tmp_path / "projects" / "helloworld" / "helloworld.py"
    assert result["success"] is True
    assert result["total_files_created"] == 1
    assert file_path.read_text(encoding="utf-8").strip() == 'print("helloworld")'
    assert result["validation"]["syntax_ok"] is True
    assert result["validation"]["run"]["stdout"] == "helloworld\n"


def test_infer_requires_simple_request_marker():
    assert module.infer_single_file_request("输出 hello 的 Python 文件") is None


def test_infer_returns_none_without_language():
    assert module.infer_single_file_request("写一个输出 hello 的脚本") is None


def test_infer_prefers_explicit_filename():
    result = module.infer_single_file_request(
        "写一个 Python 文件 script.py，输出 hello"
    )
    assert result["filename"] == "script.py"


def test_infer_defaults_to_main_and_js_extension():
    result = module.infer_single_file_request("创建一个 JavaScript 程序")
    assert result == {
        "language": "javascript",
        "extension": ".js",
        "filename": "main.js",
    }


def test_response_text_variants():
    assert module._response_text("plain") == "plain"
    assert module._response_text(
        {"choices": [{"message": {"content": "from dict"}}]}
    ) == "from dict"
    assert module._response_text({}) == ""
    assert module._response_text(
        {"choices": [{"message": "not-dict"}]}
    ) == ""


def test_safe_project_name_sanitizes():
    assert module._safe_project_name("Hello World!!") == "Hello-World"
    assert module._safe_project_name("***") == "single-file"
    assert len(module._safe_project_name("a" * 100)) == 50


def test_run_generated_file_unsupported_language(tmp_path):
    file_path = tmp_path / "a.ts"
    file_path.write_text("x", encoding="utf-8")
    result = module._run_generated_file(file_path, "typescript")
    assert result["ran"] is False
    assert result["error"] == "暂不支持该语言的运行验证"


def test_run_generated_file_timeout_and_oserror(tmp_path, monkeypatch):
    file_path = tmp_path / "a.py"
    file_path.write_text("print(1)", encoding="utf-8")

    def _timeout(*_a, **_k):
        raise module.subprocess.TimeoutExpired(cmd="x", timeout=10)

    monkeypatch.setattr(module.subprocess, "run", _timeout)
    result = module._run_generated_file(file_path, "python")
    assert result["error"] == "执行超时"

    def _oserror(*_a, **_k):
        raise OSError("no interpreter")

    monkeypatch.setattr(module.subprocess, "run", _oserror)
    result = module._run_generated_file(file_path, "python")
    assert result["error"] == "运行时环境不可用"


def test_run_generated_file_returns_nonzero_output(tmp_path, monkeypatch):
    file_path = tmp_path / "a.py"
    file_path.write_text("raise SystemExit(2)", encoding="utf-8")

    def _failing(*_a, **_k):
        return SimpleNamespace(returncode=2, stdout="", stderr="boom")

    monkeypatch.setattr(module.subprocess, "run", _failing)
    result = module._run_generated_file(file_path, "python")
    assert result["ran"] is False
    assert result["error"] == "boom"


@pytest.mark.asyncio
async def test_generate_single_file_returns_none_for_project_request():
    assert await module.generate_single_file("创建一个 FastAPI 项目") is None


@pytest.mark.asyncio
async def test_generate_single_file_empty_content(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "call_llm", AsyncMock(return_value={
        "choices": [{"message": {"content": "   "}}],
    }))
    monkeypatch.setattr(
        module, "get_dynamic_router",
        AsyncMock(return_value=SimpleNamespace(
            get_assignment=lambda *a, **k: SimpleNamespace(backend_model="m")
        )),
    )
    result = await module.generate_single_file("写一个输出 hello 的 Python 文件")
    assert result["success"] is False
    assert result["validation"]["syntax_ok"] is False
    assert result["validation"]["run"]["ran"] is False


@pytest.mark.asyncio
async def test_generate_single_file_syntax_failure(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "call_llm", AsyncMock(return_value={
        "choices": [{"message": {"content": "def broken(:"}}],
    }))
    monkeypatch.setattr(
        module, "get_dynamic_router",
        AsyncMock(return_value=SimpleNamespace(
            get_assignment=lambda *a, **k: SimpleNamespace(backend_model="m")
        )),
    )
    result = await module.generate_single_file("写一个输出 hello 的 Python 文件")
    assert result["success"] is False
    assert result["validation"]["run"]["error"] == "语法检查失败"


@pytest.mark.asyncio
async def test_generate_single_file_uses_explicit_project_name(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "call_llm", AsyncMock(return_value={
        "choices": [{"message": {"content": "print('hi')"}}],
    }))
    monkeypatch.setattr(
        module, "get_dynamic_router",
        AsyncMock(return_value=SimpleNamespace(
            get_assignment=lambda *a, **k: SimpleNamespace(backend_model="m")
        )),
    )
    result = await module.generate_single_file(
        "写一个输出 hello 的 Python 文件", project_name="My Project!"
    )
    assert result["output_dir"] == "projects/My-Project"
