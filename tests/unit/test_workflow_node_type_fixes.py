"""workflow 节点类型缺陷回归。

覆盖已建档缺陷：
- CE2 子进程输出无界收集
- CE3 超时不杀进程组
- FP2 validate_params 缺键抛 KeyError
- DT1 merge 从节点 config 读变量而非上下文
- LLM1 {{input}} 硬编码占位符
- LLM3 call_llm 返回 OpenAI 结构时提取不到 content
- CON2 表达式变量内插未转义，值含引号/花括号时语法异常
- LLM2 产出节点 output_variable 未映射进上下文，下游 input_variable 读不到
- LLM4 FALLBACK_MODEL 死常量
- GV2 on_failure 取值未约束
- EXPR1 AST 允许集合漏 ast.Load/ast.BinOp，变量引用与算术表达式被误拒
"""

import asyncio
import os
import sys
import time

import pytest
from pydantic import ValidationError

from app.schema.workflow import TaskGraph, TaskNode, TaskType
from app.utils.workflow.node_types import code_execution as code_module
from app.utils.workflow.node_types import llm_call as llm_module
from app.utils.workflow.node_types.code_execution import CodeExecutionNode
from app.utils.workflow.node_types.conditional import ConditionalNode
from app.utils.workflow.node_types.data_transform import DataTransformNode
from app.utils.workflow.node_types.file_processing import FileProcessingNode
from app.utils.workflow.node_types.llm_call import LLMCallNode
from app.utils.workflow.node_types.base import NodeResult
from app.utils.workflow.result_aggregator import ResultAggregator


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


def test_conditional_expression_handles_quote_in_value():
    """CON2：字符串值含引号时不得拼出非法表达式。"""
    node = ConditionalNode("c1", {"expression": "{name} != ''"})

    assert node._evaluate_expression("{name} != ''", {"name": "O'Brien"}) is True


def test_conditional_expression_keyword_in_data_is_not_rejected():
    """CON2：关键字检查应对模板生效，数据值含 'os.' 不应误判。"""
    node = ConditionalNode("c1", {"expression": "{path} != ''"})

    assert node._evaluate_expression("{path} != ''", {"path": "os.path"}) is True


def test_conditional_expression_rejects_forbidden_keyword_in_template():
    node = ConditionalNode("c1", {"expression": "__import__('os')"})

    with pytest.raises(ValueError):
        node._evaluate_expression("__import__('os')", {})


def test_data_transform_reduce_default_expression_runs():
    """EXPR1：reduce 默认表达式 `acc + item` 引用变量，须可用。"""
    node = DataTransformNode("d1", {})

    assert node._apply_operation("reduce", [1, 2, 3], {}) == 6
    assert node._apply_operation("reduce", [1, 2, 3], {"initial": 10}) == 16


def test_data_transform_map_handles_item_and_arithmetic():
    """EXPR1：map 默认 `item` 与 `item * 2` 均须可用。"""
    node = DataTransformNode("d1", {})

    assert node._apply_operation("map", [1, 2, 3], {}) == [1, 2, 3]
    assert node._apply_operation("map", [1, 2, 3], {"expression": "item * 2"}) == [2, 4, 6]


def test_data_transform_filter_can_reference_item_and_index():
    """EXPR1：filter 条件引用 item/index 须可用。"""
    node = DataTransformNode("d1", {})

    assert node._apply_operation("filter", [1, 2, 3], {"condition": "item > 1"}) == [2, 3]
    assert node._apply_operation(
        "filter", [9, 8, 7, 6], {"condition": "index % 2 == 0"}
    ) == [9, 7]


def test_conditional_arithmetic_expression_is_allowed():
    """EXPR1：内插后的算术表达式 `{count} + 1 > 5` 须可用。"""
    node = ConditionalNode("c1", {"expression": "{count} + 1 > 5"})

    assert node._evaluate_expression("{count} + 1 > 5", {"count": 10}) is True
    assert node._evaluate_expression("{count} + 1 > 5", {"count": 1}) is False


def test_data_transform_expression_still_rejects_dangerous_nodes():
    """EXPR1：放宽 ast.Load/ast.BinOp 后，属性/下标/调用仍须被拒。"""
    node = DataTransformNode("d1", {})

    for expression in ["item.__class__", "item[0]", "item()", "().__class__"]:
        with pytest.raises(ValueError):
            node._apply_operation("map", [1], {"expression": expression})


def _aggregator_with_llm_producer(output_variable="web_data"):
    graph = TaskGraph(
        workflow_id="agg",
        nodes=[
            TaskNode(
                id="A",
                type=TaskType.LLM_CALL,
                params={"prompt": "hello", "output_variable": output_variable},
                depends_on=[],
            ),
            TaskNode(
                id="B",
                type=TaskType.CODE_EXECUTION,
                params={"code": "print(1)"},
                depends_on=["A"],
            ),
        ],
    )
    return ResultAggregator("agg", graph)


def test_context_exposes_producer_output_variable():
    """LLM2：产出节点声明的 output_variable 应能被下游 input_variable 读到。"""
    aggregator = _aggregator_with_llm_producer()
    aggregator.record_result("A", NodeResult.success_result(data={"content": "hi"}))

    context = aggregator.get_context("B")

    assert context["web_data"] == {"content": "hi"}
    assert context["A_result"] == {"content": "hi"}


def test_context_output_variable_is_none_on_failure():
    aggregator = _aggregator_with_llm_producer()
    aggregator.record_result("A", NodeResult.error_result(error="boom"))

    context = aggregator.get_context("B")

    assert "web_data" in context
    assert context["web_data"] is None


def test_llm_call_has_no_dead_fallback_model_constant():
    """LLM4：未被引用的 FALLBACK_MODEL 已删除。"""
    assert not hasattr(llm_module, "FALLBACK_MODEL")
