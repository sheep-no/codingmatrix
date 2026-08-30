"""Integration coverage for Redis notifications and SQL-backed recovery."""

import json
import uuid

import pytest
import pytest_asyncio
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.agent.adapters.session_adapter import replay_session
from app.agent.state import MessageEnvelope, State
from app.models.Permission import Permission
from app.models.base import Base
from app.models.user import User
from app.services.task_checkpoint_service import get_latest_checkpoint, save_checkpoint
from app.services.task_event_service import append_task_event, replay_task_events
from app.services.unified_state_service import StateOwnershipError, create_task


REDIS_URL = "redis://127.0.0.1:6379/0"


@pytest_asyncio.fixture
async def test_db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def test_user(test_db: AsyncSession) -> User:
    user = User(
        id=1,
        username="state-recovery-user",
        email="state-recovery@example.com",
        hashed_password="test-hash",
    )
    test_db.add(user)
    test_db.add(Permission(user_id=1, permission_level="normal"))
    await test_db.commit()
    return user


async def _redis_client_or_skip() -> redis.Redis:
    client = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception as error:
        await client.aclose()
        pytest.skip(f"Redis 不可用，跳过 Pub/Sub 集成测试: {error}")
    return client


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_pubsub_event_is_received_for_task_update():
    client = await _redis_client_or_skip()
    channel = f"task_events:integration-{uuid.uuid4()}"
    pubsub = client.pubsub()
    await pubsub.subscribe(channel)
    try:
        await pubsub.get_message(timeout=2)
        payload = {"task_id": channel.rsplit(":", 1)[-1], "status": "running", "progress": 40}
        await client.publish(channel, json.dumps(payload))

        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
        assert message is not None
        assert json.loads(message["data"]) == payload
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await client.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sql_event_replay_and_latest_checkpoint_recover_task(test_db, test_user):
    task_id = f"integration-{uuid.uuid4()}"
    task = await create_task(test_db, test_user.id, "ppt", task_id=task_id)
    await append_task_event(
        test_db,
        task.task_id,
        test_user.id,
        "progress",
        payload={"step": "outline"},
        status="running",
        progress=40,
    )
    await append_task_event(
        test_db,
        task.task_id,
        test_user.id,
        "completed",
        payload={"artifact": "pptx"},
        status="success",
        progress=100,
    )
    await save_checkpoint(
        test_db,
        task.task_id,
        test_user.id,
        revision=1,
        step="outline",
        state={"outline": ["title"]},
        idempotency_key=f"checkpoint-{uuid.uuid4()}",
    )
    await save_checkpoint(
        test_db,
        task.task_id,
        test_user.id,
        revision=2,
        step="render",
        state={"outline": ["title"], "rendered": True},
        idempotency_key=f"checkpoint-{uuid.uuid4()}",
    )
    await test_db.commit()

    events = await replay_task_events(test_db, task.task_id, test_user.id, after_sequence=1)
    checkpoint = await get_latest_checkpoint(test_db, task.task_id, test_user.id)

    assert [event.sequence for event in events] == [2]
    assert events[0].status == "success"
    assert checkpoint is not None
    assert checkpoint.revision == 2
    assert checkpoint.state_json["rendered"] is True


@pytest.mark.integration
def test_session_replay_requests_snapshot_recovery_when_sequence_has_gap():
    state = State(
        session_id="session-integration",
        task_id="task-integration",
        revision=7,
        messages=[
            MessageEnvelope(1, "event-1", "session-integration", "task-integration", 1, 1, "progress", "integration", {"content": "outline"}),
            MessageEnvelope(1, "event-3", "session-integration", "task-integration", 3, 3, "completed", "integration", {"content": "rendered"}),
        ],
    )

    result = replay_session(state, after_sequence=0)

    assert [message["sequence"] for message in result["messages"]] == [1, 3]
    assert result["recovery_action"] == {
        "type": "snapshot_recovery",
        "task_id": "task-integration",
        "revision": 7,
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sql_replay_enforces_task_ownership(test_db, test_user):
    task = await create_task(test_db, test_user.id, "ppt", task_id=f"integration-{uuid.uuid4()}")
    await test_db.commit()

    with pytest.raises(StateOwnershipError, match="无权访问此任务"):
        await replay_task_events(test_db, task.task_id, test_user.id + 1)
