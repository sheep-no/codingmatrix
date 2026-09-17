"""任务分解与结果聚合的回归测试。

覆盖已建档缺陷：
- TDC1 retry/on_failure 字段透传
- TDC4 decompose 内部做重复 ID 与依赖存在性校验
- TDC5 提示词不再于模块导入时读盘
- TDC8 响应解析对 None content 与附带说明文字健壮
- RSA1 stream_results 不得丢失首个/末个节点事件
- RSA4 上下文只注入直接依赖结果
- RSA6 summary 的 execution_order 不得外泄内部引用
- RSA7 上下文 params 不得与节点共享引用
"""

import asyncio

import pytest

from app.schema.workflow import TaskGraph, TaskNode, TaskType
from app.utils.workflow.node_types.base import NodeResult
from app.utils.workflow.result_aggregator import ResultAggregator
from app.utils.workflow.task_decomposer import TaskDecomposer, TaskDecomposerError


def _llm_response(content):
    return {"choices": [{"message": {"content": content}}]}


def _decomposer():
    return TaskDecomposer()


def test_parse_response_keeps_retry_and_on_failure():
    response = _llm_response(
        '{"nodes": [{"id": "n1", "type": "code_execution", '
        '"params": {"code": "print(1)"}, "depends_on": [], '
        '"retry": {"max_retries": 2, "retry_delay": 1.0, "backoff_factor": 2.0}, '
        '"on_failure": "skip"}]}'
    )

    graph = _decomposer()._parse_response(response, "test")

    node = graph.nodes[0]
    assert node.on_failure == "skip"
    assert node.retry is not None
    assert node.retry.max_retries == 2


def test_parse_response_rejects_duplicate_ids():
    response = _llm_response(
        '{"nodes": ['
        '{"id": "n1", "type": "code_execution", "params": {}, "depends_on": []},'
        '{"id": "n1", "type": "code_execution", "params": {}, "depends_on": []}'
        ']}'
    )

    with pytest.raises(TaskDecomposerError):
        _decomposer()._parse_response(response, "test")


def test_parse_response_rejects_unknown_dependency():
    response = _llm_response(
        '{"nodes": [{"id": "n1", "type": "code_execution", '
        '"params": {}, "depends_on": ["missing"]}]}'
    )

    with pytest.raises(TaskDecomposerError):
        _decomposer()._parse_response(response, "test")


def test_parse_response_handles_none_content():
    response = {"choices": [{"message": {"content": None}}]}

    with pytest.raises(TaskDecomposerError):
        _decomposer()._parse_response(response, "test")


def test_parse_response_extracts_json_from_prose():
    response = _llm_response(
        '好的，任务图如下：\n{"nodes": [{"id": "n1", "type": "code_execution", '
        '"params": {}, "depends_on": []}]}\n希望有帮助。'
    )

    graph = _decomposer()._parse_response(response, "test")

    assert [node.id for node in graph.nodes] == ["n1"]


def test_system_prompt_is_not_a_class_attribute():
    """提示词改为实例化时加载，模块导入不再读盘。"""
    assert "SYSTEM_PROMPT" not in TaskDecomposer.__dict__
    assert _decomposer().system_prompt


def _graph(node_ids, aggregator_id="agg"):
    nodes = []
    for node_id in node_ids:
        depends_on = []
        if aggregator_id == "chain" and nodes:
            depends_on = [nodes[-1].id]
        nodes.append(
            TaskNode(
                id=node_id,
                type=TaskType.CODE_EXECUTION,
                params={"code": "print(1)"},
                depends_on=depends_on,
            )
        )
    return TaskGraph(workflow_id="agg", nodes=nodes)


@pytest.mark.asyncio
async def test_stream_results_emits_first_and_last_node():
    graph = _graph(["n0", "n1", "n2", "n3"])
    aggregator = ResultAggregator("agg", graph)
    events = []

    async def consume():
        async for event in aggregator.stream_results(interval=0.01):
            events.append(event)
            if event["event"] == "workflow_completed":
                return

    consumer = asyncio.create_task(consume())
    try:
        for index in range(4):
            await asyncio.sleep(0.03)
            aggregator.record_result(
                f"n{index}", NodeResult.success_result(data={"index": index})
            )
        await asyncio.wait_for(consumer, timeout=5)
    finally:
        consumer.cancel()

    node_events = [e for e in events if e["event"] == "node_completed"]
    assert [e["node_id"] for e in node_events] == ["n0", "n1", "n2", "n3"]


def test_context_only_includes_direct_dependencies():
    graph = _graph(["A", "B"])
    graph.nodes[1].depends_on = []
    graph.nodes.append(
        TaskNode(
            id="C",
            type=TaskType.CODE_EXECUTION,
            params={"code": "print(1)"},
            depends_on=["A"],
        )
    )
    aggregator = ResultAggregator("agg", graph)
    aggregator.record_result("A", NodeResult.success_result(data={"v": 1}))
    aggregator.record_result("B", NodeResult.success_result(data={"v": 2}))

    context = aggregator.get_context("C")

    assert context["A_result"] == {"v": 1}
    assert "B_result" not in context


def test_context_available_before_node_runs():
    """节点启动时（尚未 record）也能拿到上游结果。"""
    graph = _graph(["A", "B"], aggregator_id="chain")
    aggregator = ResultAggregator("agg", graph)
    aggregator.record_result("A", NodeResult.success_result(data={"v": 1}))

    context = aggregator.get_context("B")

    assert context["A_result"] == {"v": 1}


def test_summary_returns_execution_order_copy():
    graph = _graph(["A"])
    aggregator = ResultAggregator("agg", graph)
    aggregator.record_result("A", NodeResult.success_result(data={}))

    summary = aggregator.get_workflow_summary()
    summary["execution_order"].append("intruder")

    assert aggregator.get_execution_order() == ["A"]


def test_context_params_is_a_copy():
    graph = _graph(["A"])
    aggregator = ResultAggregator("agg", graph)

    context = aggregator.get_context("A")
    context["params"]["code"] = "malicious"

    assert graph.nodes[0].params["code"] == "print(1)"
