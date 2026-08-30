from unittest.mock import AsyncMock

import pytest

from app.agent.workflow_registry import build_legacy_workflow, run_workflow
from app.services import agent_state_adapter


@pytest.mark.asyncio
async def test_run_workflow_persists_state_when_context_is_provided(monkeypatch):
    definition = build_legacy_workflow("test", "/test", lambda state: {"ok": True})
    persist = AsyncMock()
    monkeypatch.setattr(agent_state_adapter, "persist_agent_state", persist)
    db = object()

    state = await run_workflow(
        definition,
        session_id="session-1",
        task_id="task-1",
        db=db,
        user_id=7,
    )

    assert state.task_id == "task-1"
    persist.assert_awaited_once_with(db, 7, state)
