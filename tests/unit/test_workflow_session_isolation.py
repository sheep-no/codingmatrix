"""会话工作流的续写上下文必须按用户隔离。

同一 session_id 被不同账号使用时，既不能读到他人历史请求，
也不能覆盖他人的会话条目；同账号续写仍须正常。
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1 import workflow
from app.schema.workflow import TaskGraph, TaskNode, TaskType, WorkflowRequest

SECRET = "A 的机密需求：收购报价 1.2 亿"
SESSION_ID = "shared-session"


def _patch_runtime(monkeypatch, workflow_id):
    graph = TaskGraph(
        workflow_id=workflow_id,
        nodes=[TaskNode(id="n1", type=TaskType.DATA_TRANSFORM)],
    )
    decomposer = MagicMock()
    decomposer.decompose = AsyncMock(return_value=graph)
    monkeypatch.setattr(workflow, "TaskDecomposer", lambda: decomposer)
    monkeypatch.setattr(workflow, "_workflows", {})

    result = SimpleNamespace(success=True, data={"value": 3}, error=None)
    aggregator = MagicMock()
    aggregator.get_all_results.return_value = {"n1": result}
    aggregator.get_workflow_summary.return_value = {"completed_nodes": 1}

    class Executor:
        def __init__(self, **kwargs):
            pass

        async def execute(self, on_node_start, on_node_complete):
            on_node_start("n1")
            on_node_complete("n1", result)
            return {"status": "completed", "summary": {"completed_nodes": 1}}

        def get_aggregator(self):
            return aggregator

    monkeypatch.setattr(workflow, "WorkflowExecutor", Executor)


async def _execute_as(user_id, text):
    db = MagicMock()
    db.commit = AsyncMock()
    request = WorkflowRequest(natural_language_request=text, session_id=SESSION_ID)
    response = await workflow.execute_workflow(request, {"sub": user_id}, db)
    return [json.loads(chunk) async for chunk in response.body_iterator]


def _started(events):
    return next(e for e in events if e["event"] == "workflow_started")


@pytest.mark.asyncio
async def test_owner_receives_continuation_context(monkeypatch):
    _patch_runtime(monkeypatch, "w-first")
    monkeypatch.setattr(workflow, "_session_workflows", {})

    await _execute_as("42", SECRET)
    events = await _execute_as("42", "继续扩展")

    assert _started(events)["is_continuation"] is True
    continuation = [e for e in events if e["event"] == "continuation_context"]
    assert len(continuation) == 1
    assert continuation[0]["previous_request"] == SECRET


@pytest.mark.asyncio
async def test_other_account_cannot_read_or_overwrite_session(monkeypatch):
    _patch_runtime(monkeypatch, "w-second")
    monkeypatch.setattr(workflow, "_session_workflows", {})

    owner_events = await _execute_as("42", SECRET)
    intruder_events = await _execute_as("43", "继续扩展")

    assert _started(intruder_events)["is_continuation"] is False
    assert [e for e in intruder_events if e["event"] == "continuation_context"] == []
    assert SECRET not in json.dumps(intruder_events, ensure_ascii=False)

    # 入侵者写入不得覆盖属主条目
    owner_again = await _execute_as("42", "继续扩展")
    continuation = [e for e in owner_again if e["event"] == "continuation_context"]
    assert len(continuation) == 1
    assert continuation[0]["previous_request"] == SECRET
    assert _started(owner_events)["is_continuation"] is False
