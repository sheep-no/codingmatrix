from unittest.mock import AsyncMock

import pytest

from app.agent.state.models import MessageEnvelope, State
from app.services import agent_state_adapter


@pytest.mark.asyncio
async def test_persist_agent_state_writes_checkpoint_events_and_artifacts(monkeypatch):
    db = AsyncMock()
    state = State(
        session_id="session-1",
        task_id="task-1",
        revision=2,
        status="running",
        messages=[MessageEnvelope(1, "event-1", "session-1", "task-1", 2, 1, "node_completed", "agent", {"node": "generate"})],
        generated_files=[{"path": "src/main.py", "content_hash": "abc"}],
    )
    session = type("Session", (), {"id": "unified-session"})()
    monkeypatch.setattr(agent_state_adapter, "ensure_project_session", AsyncMock(return_value=session))
    monkeypatch.setattr(agent_state_adapter, "save_graph_checkpoint", AsyncMock(return_value="task-1"))
    append = AsyncMock()
    artifact = AsyncMock()
    monkeypatch.setattr(agent_state_adapter, "append_task_event", append)
    monkeypatch.setattr(agent_state_adapter, "create_artifact", artifact)

    result = await agent_state_adapter.persist_agent_state(db, 7, state)

    assert result == "task-1"
    assert agent_state_adapter.save_graph_checkpoint.await_args.args[2].session_id == "unified-session"
    append.assert_awaited_once()
    artifact.assert_awaited_once()
    db.commit.assert_awaited_once()
