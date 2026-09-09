"""Workflow snapshots use live execution state without calling providers."""
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import AsyncMock
import json
import pytest
from fastapi import HTTPException
from app.api.v1 import workflow
from app.schema.workflow import TaskGraph, TaskNode, TaskType, WorkflowRequest


@pytest.mark.asyncio
async def test_status_returns_live_results_for_owner(monkeypatch):
    graph = TaskGraph(workflow_id="w1", nodes=[TaskNode(id="n1", type=TaskType.DATA_TRANSFORM)])
    aggregator = MagicMock()
    aggregator.get_all_results.return_value = {"n1": SimpleNamespace(success=True, data={"value": 3}, error=None)}
    aggregator.get_workflow_summary.return_value = {"completed_nodes": 1}
    executor = MagicMock()
    executor.get_aggregator.return_value = aggregator
    monkeypatch.setattr(workflow, "_workflows", {"w1": {"user_id": "42", "task_graph": graph, "executor": executor, "status": "completed"}})
    result = await workflow.get_workflow_status("w1", {"sub": "42"})
    assert result["status"] == "completed"
    assert result["task_graph"]["nodes"][0]["result"] == {"value": 3}
    assert result["summary"]["completed_nodes"] == 1


@pytest.mark.asyncio
async def test_status_unavailable_for_other_account(monkeypatch):
    monkeypatch.setattr(workflow, "_workflows", {"w1": {"user_id": "42"}})
    with pytest.raises(HTTPException) as error:
        await workflow.get_workflow_status("w1", {"sub": "43"})
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_execute_emits_real_ndjson_contract_with_fake_execution(monkeypatch):
    graph = TaskGraph(workflow_id="mock-run", nodes=[TaskNode(id="n1", type=TaskType.DATA_TRANSFORM)])
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
    db = MagicMock()
    db.commit = AsyncMock()
    response = await workflow.execute_workflow(WorkflowRequest(natural_language_request="test"), {"sub": "42"}, db)
    events = [json.loads(chunk) async for chunk in response.body_iterator]
    assert response.media_type == "application/x-ndjson"
    assert [event["event"] for event in events] == ["workflow_started", "task_graph_generated", "node_started", "node_completed", "workflow_completed"]
    assert events[-1]["status"] == "completed"
    snapshot = await workflow.get_workflow_status("mock-run", {"sub": "42"})
    assert snapshot["summary"]["completed_nodes"] == 1
