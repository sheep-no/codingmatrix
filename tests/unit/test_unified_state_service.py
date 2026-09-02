import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.task import Task
from app.models.unified_state import Artifact, Checkpoint, Message, Session, TaskEvent
from app.services.unified_state_service import (
    StateOwnershipError,
    append_message,
    append_task_event,
    create_artifact,
    create_session,
    create_task,
    list_messages,
    replay_task_events,
    save_checkpoint,
    transition_task,
)


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
async def test_unified_state_lifecycle_and_replay(db):
    session = await create_session(db, 1, "ppt")
    await append_message(db, session.id, 1, "user", "生成季度汇报")
    await append_message(db, session.id, 1, "assistant", "已开始")
    messages = await list_messages(db, session.id, 1)
    task = await create_task(db, 1, "ppt_generation", session_id=session.id)
    await transition_task(db, task.task_id, 1, "running", 20, "outline")
    await append_task_event(db, task.task_id, 1, "progress", {"step": "outline"}, "running", 20)
    await save_checkpoint(db, task.task_id, 1, 1, "outline", {"slides": []}, "outline-1")
    artifact = await create_artifact(db, 1, "pptx", "pptx_output/a.pptx", task.task_id, session.id)
    events = await replay_task_events(db, task.task_id, 1)

    assert [message.sequence for message in messages] == [1, 2]
    assert events[0].sequence == 1
    assert artifact.task_id == task.task_id


@pytest.mark.asyncio
async def test_unified_state_enforces_ownership(db):
    session = await create_session(db, 1, "ppt")
    with pytest.raises(StateOwnershipError):
        await append_message(db, session.id, 2, "user", "越权")
