"""工作流执行健壮性回归。

覆盖已建档缺陷：
- WFE1/STM4 失败节点阻塞后续节点时工作流必须收尾为 FAILED，而非永久 RUNNING
- WFE2 cancel() 必须取消运行中的节点任务，避免后台继续消耗资源
- WF1  会话工作流字典必须有容量上限，避免无界增长
- WF4  客户端断开（stream 关闭）时必须取消仍在运行的执行
"""

import asyncio
import json
from datetime import datetime, timedelta

import pytest

from app.api.v1 import workflow as workflow_api
from app.api.v1.workflow import execute_workflow
from app.schema.workflow import TaskGraph, TaskNode, TaskType, WorkflowRequest
from app.utils.workflow.executor import WorkflowExecutor
from app.utils.workflow.node_types.base import NodeResult


def _node(node_id, depends_on=None, task_type=TaskType.CODE_EXECUTION):
    return TaskNode(
        id=node_id,
        type=task_type,
        params={"code": "print(1)"},
        depends_on=depends_on or [],
    )


@pytest.mark.asyncio
async def test_failed_node_blocking_siblings_ends_workflow_failed(monkeypatch):
    """A 失败、B 依赖 A、C 独立：执行结束后状态必须是 failed。"""
    graph = TaskGraph(
        workflow_id="wfe1",
        nodes=[_node("A"), _node("B", ["A"]), _node("C")],
    )

    async def fake_execute_node(self, node_id, context, cancel_event):
        if node_id == "A":
            return NodeResult.error_result(error="boom")
        return NodeResult.success_result(data={"ok": node_id})

    monkeypatch.setattr(WorkflowExecutor, "_execute_node", fake_execute_node)

    executor = WorkflowExecutor(graph, max_concurrent=1)
    result = await executor.execute()

    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_cancel_cancels_running_node_task(monkeypatch):
    """cancel() 后运行中的节点任务必须收到取消信号。"""
    graph = TaskGraph(workflow_id="wfe2", nodes=[_node("A")])
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def slow_execute_node(self, node_id, context, cancel_event):
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return NodeResult.success_result(data={})

    monkeypatch.setattr(WorkflowExecutor, "_execute_node", slow_execute_node)

    executor = WorkflowExecutor(graph)
    execution = asyncio.create_task(executor.execute())
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        executor.cancel()
        await asyncio.wait_for(cancelled.wait(), timeout=5)
        await asyncio.wait_for(execution, timeout=5)
    finally:
        execution.cancel()


def test_session_workflows_evict_oldest(monkeypatch):
    """会话工作流字典达到上限时淘汰最旧记录。"""
    monkeypatch.setattr(workflow_api, "_MAX_SESSION_WORKFLOWS", 3)
    workflow_api._session_workflows.clear()
    try:
        now = datetime.now()
        for index in range(4):
            workflow_api._remember_session_workflow(
                "u1",
                f"s{index}",
                {"updated_at": (now - timedelta(minutes=10 - index)).isoformat()},
            )

        assert len(workflow_api._session_workflows) == 3
        assert ("u1", "s0") not in workflow_api._session_workflows
        assert ("u1", "s3") in workflow_api._session_workflows
    finally:
        workflow_api._session_workflows.clear()


@pytest.mark.asyncio
async def test_stream_close_cancels_running_executor(monkeypatch):
    """客户端断开导致 stream 关闭时，必须调用 executor.cancel()。"""
    graph = TaskGraph(workflow_id="wf4", nodes=[_node("n1")])
    created = []

    class FakeDecomposer:
        def __init__(self, *args, **kwargs):
            pass

        async def decompose(self, request):
            return graph

    class FakeExecutor:
        def __init__(self, **kwargs):
            self.cancelled = False
            created.append(self)

        async def execute(self, **kwargs):
            await asyncio.sleep(30)

        def cancel(self):
            self.cancelled = True

    async def fake_drain(queue, timeout=0.05):
        yield json.dumps({"event": "noop"}) + "\n"

    monkeypatch.setattr(workflow_api, "TaskDecomposer", FakeDecomposer)
    monkeypatch.setattr(workflow_api, "WorkflowExecutor", FakeExecutor)
    monkeypatch.setattr(workflow_api, "_drain_event_queue", fake_drain)

    response = await execute_workflow(
        request=WorkflowRequest(natural_language_request="test"),
        token={"sub": "u1"},
        db=None,
    )
    stream = response.body_iterator

    await anext(stream)  # workflow_started
    await anext(stream)  # task_graph_generated
    await anext(stream)  # 进入执行段，executor 已创建

    assert created
    assert created[0].cancelled is False

    await stream.aclose()

    assert created[0].cancelled is True
