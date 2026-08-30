import pytest

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
