"""agent_state_adapter 分支补测。"""

from unittest.mock import AsyncMock

import pytest

from app.agent.state.models import State
from app.services import agent_state_adapter


@pytest.mark.asyncio
async def test_ensure_project_session_creates_mapping_when_session_missing(monkeypatch):
    db = AsyncMock()
    mapping = type("Mapping", (), {"unified_id": "stale-session"})()
    created = type("Session", (), {"id": "session-2"})()
    monkeypatch.setattr(
        agent_state_adapter,
        "resolve_compatibility_mapping",
        AsyncMock(return_value=mapping),
    )
    db.get.return_value = None
    monkeypatch.setattr(
        agent_state_adapter, "create_session", AsyncMock(return_value=created)
    )
    upsert = AsyncMock()
    monkeypatch.setattr(agent_state_adapter, "upsert_compatibility_mapping", upsert)

    result = await agent_state_adapter.ensure_project_session(db, 7, "legacy-1", title="Demo")

    assert result is created
    upsert.assert_awaited_once()
    assert upsert.await_args.args[4] == "legacy-1"


@pytest.mark.asyncio
async def test_ensure_project_session_creates_session_when_no_mapping(monkeypatch):
    db = AsyncMock()
    created = type("Session", (), {"id": "session-3"})()
    monkeypatch.setattr(
        agent_state_adapter,
        "resolve_compatibility_mapping",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        agent_state_adapter, "create_session", AsyncMock(return_value=created)
    )
    upsert = AsyncMock()
    monkeypatch.setattr(agent_state_adapter, "upsert_compatibility_mapping", upsert)

    result = await agent_state_adapter.ensure_project_session(db, 7, "legacy-2")

    assert result is created
    upsert.assert_awaited_once()
    db.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_graph_checkpoint_persists_revision_and_returns_task(monkeypatch):
    db = AsyncMock()
    task = type("Task", (), {"task_id": "task-9"})()
    create_task = AsyncMock(return_value=task)
    save_checkpoint = AsyncMock()
    monkeypatch.setattr(agent_state_adapter, "create_task", create_task)
    monkeypatch.setattr(agent_state_adapter, "save_checkpoint", save_checkpoint)
    state = State(session_id="session-1", task_id="task-9", revision=4)

    result = await agent_state_adapter.save_graph_checkpoint(db, 7, state)

    assert result == "task-9"
    create_task.assert_awaited_once()
    kwargs = save_checkpoint.await_args.kwargs
    assert kwargs["revision"] == 4
    assert kwargs["idempotency_key"] == "agent-graph:task-9:4"


@pytest.mark.asyncio
async def test_save_graph_checkpoint_forwards_explicit_idempotency_key(monkeypatch):
    db = AsyncMock()
    task = type("Task", (), {"task_id": "task-9"})()
    monkeypatch.setattr(
        agent_state_adapter, "create_task", AsyncMock(return_value=task)
    )
    save_checkpoint = AsyncMock()
    monkeypatch.setattr(agent_state_adapter, "save_checkpoint", save_checkpoint)
    state = State(session_id="session-1", task_id="task-9", revision=1)

    await agent_state_adapter.save_graph_checkpoint(db, 7, state, "custom-key")

    assert save_checkpoint.await_args.kwargs["idempotency_key"] == "custom-key"


@pytest.mark.asyncio
async def test_persist_agent_state_skips_unchanged_model_context(monkeypatch):
    from app.services import model_context_service

    db = AsyncMock()
    state = State(
        session_id="session-1",
        task_id="task-1",
        revision=1,
        metadata={"model_context": {"config_version": 2, "roles": {"main": "m"}}},
    )
    session = type("Session", (), {"id": "unified-session"})()
    monkeypatch.setattr(
        agent_state_adapter, "ensure_project_session", AsyncMock(return_value=session)
    )
    monkeypatch.setattr(
        agent_state_adapter, "save_graph_checkpoint", AsyncMock(return_value="task-1")
    )
    monkeypatch.setattr(
        model_context_service,
        "get_model_context",
        AsyncMock(return_value={"config_version": 2, "roles": {"main": "m"}}),
    )
    save_context = AsyncMock()
    monkeypatch.setattr(model_context_service, "save_model_context", save_context)

    await agent_state_adapter.persist_agent_state(db, 7, state)

    save_context.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_agent_state_saves_changed_model_context(monkeypatch):
    from app.services import model_context_service

    db = AsyncMock()
    state = State(
        session_id="session-1",
        task_id="task-1",
        revision=1,
        metadata={"model_context": {"config_version": 2}},
    )
    session = type("Session", (), {"id": "unified-session"})()
    monkeypatch.setattr(
        agent_state_adapter, "ensure_project_session", AsyncMock(return_value=session)
    )
    monkeypatch.setattr(
        agent_state_adapter, "save_graph_checkpoint", AsyncMock(return_value="task-1")
    )
    monkeypatch.setattr(
        model_context_service, "get_model_context", AsyncMock(return_value=None)
    )
    save_context = AsyncMock()
    monkeypatch.setattr(model_context_service, "save_model_context", save_context)

    await agent_state_adapter.persist_agent_state(db, 7, state)

    save_context.assert_awaited_once()
    assert save_context.await_args.args[3] == {"config_version": 2}
