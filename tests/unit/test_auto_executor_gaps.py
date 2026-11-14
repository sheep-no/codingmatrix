"""auto_executor LLM 循环分支补测。"""

import pytest

from app.utils.aicloud import auto_executor as module
from app.utils.aicloud.auto_executor import execute_with_llm_loop, extract_code_blocks


def _resp(content):
    return {"choices": [{"message": {"content": content}}]}


async def test_malformed_response_dict_returns_error():
    async def llm(**kwargs):
        return {"choices": []}

    result = await execute_with_llm_loop("hi", "", "", "m", 10, llm)
    assert result == "抱歉，AI 响应格式错误"


async def test_non_dict_response_returns_error():
    async def llm(**kwargs):
        return "plain string"

    result = await execute_with_llm_loop("hi", "", "", "m", 10, llm)
    assert result == "抱歉，AI 响应格式错误"


async def test_llm_exception_returns_availability_message():
    async def llm(**kwargs):
        raise RuntimeError("x" * 300)

    result = await execute_with_llm_loop("hi", "", "", "m", 10, llm)
    assert result.startswith("抱歉，AI 服务暂时不可用:")
    assert len(result) <= len("抱歉，AI 服务暂时不可用: ") + 100


async def test_no_code_block_returns_content():
    async def llm(**kwargs):
        return _resp("just text")

    result = await execute_with_llm_loop("hi", "", "", "m", 10, llm)
    assert result == "just text"


async def test_unsafe_code_injects_warning():
    prompts = []

    async def llm(**kwargs):
        prompts.append(kwargs["prompt"])
        if len(prompts) == 1:
            return _resp("```python\nimport os\n```")
        return _resp("done")

    result = await execute_with_llm_loop("hi", "", "", "m", 10, llm)

    assert result == "done"
    assert "[WARNING] 代码安全检查未通过" in prompts[1]


async def test_successful_execution_injects_output(tmp_path):
    prompts = []

    async def llm(**kwargs):
        prompts.append(kwargs["prompt"])
        if len(prompts) == 1:
            return _resp("```python\nprint('ok')\n```")
        return _resp("finished")

    result = await execute_with_llm_loop(
        "hi", "", "", "m", 10, llm, workspace_path=str(tmp_path)
    )

    assert result == "finished"
    assert "[SUCCESS] 代码执行成功" in prompts[1]
    assert "ok" in prompts[1]


async def test_failed_execution_injects_error(tmp_path):
    prompts = []

    async def llm(**kwargs):
        prompts.append(kwargs["prompt"])
        if len(prompts) == 1:
            return _resp("```python\nraise ValueError('nope')\n```")
        return _resp("finished")

    result = await execute_with_llm_loop(
        "hi", "", "", "m", 10, llm, workspace_path=str(tmp_path)
    )

    assert result == "finished"
    assert "[ERROR] 代码执行失败" in prompts[1]
    assert "nope" in prompts[1]


async def test_executor_exception_injects_error(monkeypatch, tmp_path):
    class Broken:
        def __init__(self, workspace_path=None):
            pass

        async def execute(self, **kwargs):
            raise RuntimeError("sandbox exploded")

    monkeypatch.setattr(module, "CodeExecutor", Broken)
    prompts = []

    async def llm(**kwargs):
        prompts.append(kwargs["prompt"])
        if len(prompts) == 1:
            return _resp("```python\nprint(1)\n```")
        return _resp("finished")

    result = await execute_with_llm_loop("hi", "", "", "m", 10, llm)

    assert result == "finished"
    assert "[ERROR] 代码执行异常: sandbox exploded" in prompts[1]


async def test_max_iterations_appends_notice(monkeypatch):
    monkeypatch.setattr(module, "MAX_EXECUTE_ITERATIONS", 2)

    async def llm(**kwargs):
        return _resp("```python\nprint(1)\n```")

    result = await execute_with_llm_loop("hi", "", "", "m", 10, llm)

    assert result.startswith("```python")
    assert "已达到最大自动执行次数" in result


async def test_execution_success_with_stderr_warning(tmp_path, monkeypatch):
    class Result:
        success = True
        output = "out"
        error = "warn"
        exit_code = 0

    class FakeExecutor:
        def __init__(self, workspace_path=None):
            pass

        async def execute(self, **kwargs):
            return Result()

    monkeypatch.setattr(module, "CodeExecutor", FakeExecutor)
    prompts = []

    async def llm(**kwargs):
        prompts.append(kwargs["prompt"])
        return _resp("```python\nx\n```") if len(prompts) == 1 else _resp("done")

    await execute_with_llm_loop("hi", "", "", "m", 10, llm)

    assert "警告/Stderr:\nwarn" in prompts[1]


def test_extract_multiple_blocks():
    text = "```python\na\n```\ntext\n```python\nb\n```"
    assert extract_code_blocks(text) == ["a", "b"]
