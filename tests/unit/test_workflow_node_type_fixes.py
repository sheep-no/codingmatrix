"""workflow 节点类型缺陷回归。

覆盖已建档缺陷：
- CE2 子进程输出无界收集
- CE3 超时不杀进程组
- FP2 validate_params 缺键抛 KeyError
- DT1 merge 从节点 config 读变量而非上下文
- LLM1 {{input}} 硬编码占位符
- LLM3 call_llm 返回 OpenAI 结构时提取不到 content
- GV2 on_failure 取值未约束
"""

import asyncio
import os
import sys
import time

import pytest
from pydantic import ValidationError

from app.schema.workflow import TaskNode, TaskType
from app.utils.workflow.node_types import code_execution as code_module
from app.utils.workflow.node_types import llm_call as llm_module
from app.utils.workflow.node_types.code_execution import CodeExecutionNode
from app.utils.workflow.node_types.data_transform import DataTransformNode
from app.utils.workflow.node_types.file_processing import FileProcessingNode
from app.utils.workflow.node_types.llm_call import LLMCallNode


@pytest.mark.asyncio
async def test_code_execution_truncates_large_output():
    node = CodeExecutionNode("n1", {"code": "print('x' * 2000000)"})

    result = await node._execute_python("print('x' * 2000000)", timeout=30)

    assert len(result["stdout"]) <= code_module._MAX_OUTPUT_BYTES
    assert len(result["stdout"]) > 0
    assert result["exit_code"] == 0


@pytest.mark.asyncio
async def test_code_execution_kills_process_group_on_timeout(tmp_path):
    pid_file = tmp_path / "child_pid.txt"
    # 孙进程把 stdio 指向 DEVNULL，避免它继承父进程管道而在测试收尾时挂起；
    # 超时必须杀掉整个进程组，否则孙进程会逃逸并继续运行
    code = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen(\n"
        "    [sys.executable, '-c', 'import time; time.sleep(120)'],\n"
        "    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,\n"
        ")\n"
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
        "time.sleep(120)\n"
    )
    node = CodeExecutionNode("n1", {"code": code})

    try:
        with pytest.raises(asyncio.TimeoutError):
            await node._execute_python(code, timeout=1)

        child_pid = int(pid_file.read_text())
        # 孙进程被杀后可能短暂处于僵尸态，等待其真正停止运行
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                state = open(f"/proc/{child_pid}/stat").read().split(") ", 1)[1].split()[0]
            except FileNotFoundError:
                state = None
            if state is None or state == "Z":
                break
            time.sleep(0.05)
        assert state is None or state == "Z", f"孙进程仍在运行: {state}"
    finally:
        # 修复缺失时孙进程可能仍在运行，收尾时清理避免污染环境
        if pid_file.exists():
            stray_pid = int(pid_file.read_text())
            try:
                os.kill(stray_pid, 9)
            except (ProcessLookupError, PermissionError):
                pass


def test_file_processing_missing_path_reports_error():
    node = FileProcessingNode("n1", {"operation": "read"})

    errors = node.validate_params()

    assert errors
    assert any("path" in error for error in errors)


def test_file_processing_missing_copy_source_reports_error():
    node = FileProcessingNode("n1", {"operation": "copy", "destination": "/tmp/x"})

    errors = node.validate_params()

    assert any("source" in error for error in errors)


@pytest.mark.asyncio
async def test_data_transform_merge_reads_from_context():
    node = DataTransformNode(
        "n1",
        {
            "operation": "merge",
            "input_variable": "a_result",
            "config": {"variables": ["b_result"]},
        },
    )

    result = await node.execute(
        {"a_result": {"x": 1}, "b_result": {"y": 2}}
    )

    assert result.success is True
    assert result.data["result"] == {"x": 1, "y": 2}


@pytest.mark.asyncio
async def test_llm_call_extracts_openai_style_content(monkeypatch):
    async def fake_call_llm(**kwargs):
        return {"choices": [{"message": {"content": "hello"}}]}

    monkeypatch.setattr(llm_module, "call_llm", fake_call_llm)
    node = LLMCallNode("n1", {"prompt": "hi"})

    result = await node.execute({})

    assert result.success is True
    assert result.data["content"] == "hello"


@pytest.mark.asyncio
@pytest.mark.parametrize("placeholder", ["{{input}}", "{input}"])
async def test_llm_call_replaces_input_placeholder(monkeypatch, placeholder):
    captured = {}

    async def fake_call_llm(**kwargs):
        captured.update(kwargs)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(llm_module, "call_llm", fake_call_llm)
    node = LLMCallNode(
        "n1",
        {"prompt": f"数据：{placeholder}", "input_variable": "a_result"},
    )

    result = await node.execute({"a_result": "PAYLOAD"})

    assert result.success is True
    assert "PAYLOAD" in captured["prompt"]
    assert placeholder not in captured["prompt"]


@pytest.mark.asyncio
async def test_llm_call_appends_input_when_no_placeholder(monkeypatch):
    captured = {}

    async def fake_call_llm(**kwargs):
        captured.update(kwargs)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(llm_module, "call_llm", fake_call_llm)
    node = LLMCallNode(
        "n1",
        {"prompt": "总结", "input_variable": "a_result"},
    )

    await node.execute({"a_result": "PAYLOAD"})

    assert "PAYLOAD" in captured["prompt"]


def test_task_node_rejects_invalid_on_failure():
    with pytest.raises(ValidationError):
        TaskNode(
            id="n1",
            type=TaskType.CODE_EXECUTION,
            params={},
            on_failure="bogus",
        )


def test_on_failure_normalization_falls_back_to_fail():
    from app.utils.workflow.task_decomposer import _normalize_on_failure

    assert _normalize_on_failure(None) == "fail"
    assert _normalize_on_failure("skip") == "skip"
    assert _normalize_on_failure("bogus") == "fail"
