from unittest.mock import AsyncMock

import pytest

from app.agent.state.models import State
from app.services import agent_state_adapter, workflow_state_adapter


@pytest.mark.asyncio
async def test_agent_session_mapping_is_idempotent(monkeypatch):
    db = AsyncMock()
    mapping = type("Mapping", (), {"unified_id": "session-1"})()
    session = object()
    monkeypatch.setattr(agent_state_adapter, "resolve_compatibility_mapping", AsyncMock(return_value=mapping))
    db.get.return_value = session

    assert await agent_state_adapter.ensure_project_session(db, 7, "legacy-1") is session
    db.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_workflow_stage_delegates_to_unified_event(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(workflow_state_adapter, "ensure_workflow_task", AsyncMock(return_value="task-1"))
    append = AsyncMock()
    monkeypatch.setattr(workflow_state_adapter, "append_task_event", append)

    result = await workflow_state_adapter.record_workflow_stage(
        db, 7, "workflow-1", "node_completed", {"node": "generate"}, "running", 50
    )

    assert result == "task-1"
    append.assert_awaited_once_with(db, "task-1", 7, "node_completed", {"node": "generate"}, "running", 50)


def test_agent_state_is_serializable_for_checkpoint():
    state = State(session_id="session-1", task_id="task-1", revision=2)
    assert state.to_dict()["revision"] == 2
