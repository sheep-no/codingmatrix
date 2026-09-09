import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.state.models import State
from app.db.models import ProjectSession
from app.models.base import Base
from app.models.task import Task
from app.models.unified_state import Checkpoint
from app.api.v1.ai_agent.model_context_endpoints import (
    read_agent_model_context,
    update_agent_model_context,
)
from app.api.v1.ai_agent.schemas import AgentModelContextUpdate
from app.services.model_context_service import get_model_context, save_model_context
from app.services.agent_state_adapter import ensure_project_session, persist_agent_state
from app.services.unified_state_service import StateConflictError, create_session


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_model_context_uses_an_independent_revision_stream(db):
    session = await create_session(db, 1, "agent", external_id="legacy-session")

    await save_model_context(db, 1, session.id, {
        "config_version": "3.1",
        "roles": {"architect": "model-a"},
        "assignments": {"architect": {"model": "model-a", "calls": 0}},
    })
    await save_model_context(db, 1, session.id, {
        "current_model": "model-a",
        "current_agent": "architect",
        "assignments": {"architect": {"calls": 2, "success_rate": 95}},
    })

    context = await get_model_context(db, 1, session.id)
    task = await db.scalar(select(Task).where(Task.task_type == "agent_model_context"))
    checkpoints = list((await db.scalars(
        select(Checkpoint)
        .where(Checkpoint.task_id == task.task_id)
        .order_by(Checkpoint.revision)
    )).all())

    assert [checkpoint.revision for checkpoint in checkpoints] == [1, 2]
    assert context["roles"]["architect"] == "model-a"
    assert context["assignments"]["architect"] == {
        "model": "model-a", "calls": 2, "success_rate": 95
    }
    assert context["current_model"] == "model-a"


@pytest.mark.asyncio
async def test_model_context_api_restores_owned_session(db):
    db.add(ProjectSession(
        session_id="session-1",
        user_id="1",
        requirement="test model context",
    ))
    await db.flush()
    payload = AgentModelContextUpdate(
        expected_revision=0,
        config_version="3.1",
        current_model="model-a",
        current_agent="architect",
        roles={"architect": "model-a"},
    )
    updated = await update_agent_model_context("session-1", payload, {"sub": "1"}, db)
    restored = await read_agent_model_context("session-1", {"sub": "1"}, db)

    assert updated.found is True
    assert updated.revision == 1
    assert restored.found is True
    assert restored.revision == 1
    assert restored.context["current_model"] == "model-a"

    with pytest.raises(HTTPException) as error:
        await read_agent_model_context("session-1", {"sub": "2"}, db)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_model_context_rejects_a_stale_revision(db):
    session = await create_session(db, 1, "agent", external_id="legacy-session")
    first = await save_model_context(db, 1, session.id, {"current_model": "model-a"})

    with pytest.raises(StateConflictError):
        await save_model_context(
            db,
            1,
            session.id,
            {"current_model": "model-b"},
            expected_revision=first.revision - 1,
        )

    context = await get_model_context(db, 1, session.id)
    assert context["current_model"] == "model-a"


@pytest.mark.asyncio
async def test_model_context_replaces_removed_roles(db):
    session = await create_session(db, 1, "agent", external_id="legacy-session")
    first = await save_model_context(db, 1, session.id, {
        "roles": {"architect": "model-a", "reviewer": "model-b"},
        "assignments": {
            "architect": {"model": "model-a", "calls": 1},
            "reviewer": {"model": "model-b", "calls": 2},
        },
    })

    updated = await save_model_context(
        db,
        1,
        session.id,
        {"roles": {"architect": "model-a"}},
        expected_revision=first.revision,
    )

    assert updated.context["roles"] == {"architect": "model-a"}
    assert set(updated.context["assignments"]) == {"architect"}


@pytest.mark.asyncio
async def test_model_context_api_can_clear_current_model(db):
    db.add(ProjectSession(
        session_id="session-2",
        user_id="1",
        requirement="test nullable fields",
    ))
    await db.flush()
    created = await update_agent_model_context(
        "session-2",
        AgentModelContextUpdate(
            expected_revision=0,
            current_model="model-a",
            current_agent="architect",
        ),
        {"sub": "1"},
        db,
    )

    cleared = await update_agent_model_context(
        "session-2",
        AgentModelContextUpdate(
            expected_revision=created.revision,
            current_model=None,
            current_agent=None,
        ),
        {"sub": "1"},
        db,
    )

    assert cleared.context["current_model"] is None
    assert cleared.context["current_agent"] is None
    assert cleared.revision == created.revision + 1


@pytest.mark.asyncio
async def test_graph_runtime_config_preserves_observed_model_stats(db):
    session = await ensure_project_session(db, 1, "legacy-session")
    await save_model_context(db, 1, session.id, {
        "config_version": "3.1",
        "roles": {"architect": "model-a"},
        "current_model": "model-a",
        "current_agent": "architect",
        "assignments": {
            "architect": {"model": "model-a", "calls": 2, "success_rate": 95}
        },
        "fallback_history": [{"from_model": "model-b", "to_model": "model-a"}],
    })
    state = State(
        session_id="legacy-session",
        task_id="graph-task",
        metadata={
            "model_context": {
                "config_version": "3.1",
                "roles": {"architect": "model-a"},
            }
        },
    )

    await persist_agent_state(db, 1, state)

    context = await get_model_context(db, 1, session.id)
    assert context["current_model"] == "model-a"
    assert context["assignments"]["architect"]["calls"] == 2
    assert context["fallback_history"] == [
        {"from_model": "model-b", "to_model": "model-a"}
    ]
