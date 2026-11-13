"""补测 unified_state_service 的错误分支、幂等与租约/快照逻辑。"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.services import unified_state_service as svc


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


class _Nested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _ConflictDB:
    """让 flush 稳定抛 IntegrityError，用于驱动预留冲突分支。"""

    def __init__(self, message):
        self.message = message
        self.flushes = 0

    async def scalar(self, stmt):
        return 1

    def add(self, obj):
        pass

    def begin_nested(self):
        return _Nested()

    async def flush(self):
        self.flushes += 1
        raise IntegrityError("stmt", {}, Exception(self.message))


@pytest.fixture
def fake_session(monkeypatch):
    session = SimpleNamespace(id="sess-1", updated_at=None)

    async def fake_get_owned_session(db, session_id, user_id):
        return session

    monkeypatch.setattr(svc, "get_owned_session", fake_get_owned_session)
    return session


class TestSessionLookup:
    @pytest.mark.asyncio
    async def test_missing_session_raises_not_found(self, db):
        with pytest.raises(svc.StateNotFoundError):
            await svc.get_owned_session(db, "missing", 1)

    @pytest.mark.asyncio
    async def test_foreign_session_raises_ownership(self, db):
        session = await svc.create_session(db, 1, "ppt")
        with pytest.raises(svc.StateOwnershipError):
            await svc.get_owned_session(db, session.id, 2)


class TestListMessages:
    @pytest.mark.asyncio
    async def test_before_sequence_filters_older_messages(self, db):
        session = await svc.create_session(db, 1, "ppt")
        await svc.append_message(db, session.id, 1, "user", "one")
        await svc.append_message(db, session.id, 1, "user", "two")
        await svc.append_message(db, session.id, 1, "user", "three")

        messages = await svc.list_messages(db, session.id, 1, before_sequence=3)

        assert [m.content for m in messages] == ["one", "two"]

    @pytest.mark.asyncio
    async def test_limit_is_clamped_to_at_least_one(self, db):
        session = await svc.create_session(db, 1, "ppt")
        await svc.append_message(db, session.id, 1, "user", "one")

        assert len(await svc.list_messages(db, session.id, 1, limit=0)) == 1


class TestReserveSessionEventConflicts:
    @pytest.mark.asyncio
    async def test_expected_conflict_returns_existing_event(
        self, monkeypatch, fake_session
    ):
        fake_db = _ConflictDB("uq_session_events_session_turn")
        existing = SimpleNamespace(id="evt-1")
        calls = {"n": 0}

        async def fake_lookup(db, session_id, user_id, turn_id):
            calls["n"] += 1
            return None if calls["n"] == 1 else existing

        monkeypatch.setattr(svc, "get_session_event_by_turn_id", fake_lookup)

        event, created = await svc.reserve_session_event(
            fake_db, "sess-1", 1, "type", "turn-1"
        )

        assert event is existing
        assert created is False

    @pytest.mark.asyncio
    async def test_unexpected_integrity_error_is_reraised(self, monkeypatch, fake_session):
        async def no_existing(db, session_id, user_id, turn_id):
            return None

        monkeypatch.setattr(svc, "get_session_event_by_turn_id", no_existing)
        fake_db = _ConflictDB("some other constraint")

        with pytest.raises(IntegrityError):
            await svc.reserve_session_event(fake_db, "sess-1", 1, "type", "turn-1")

    @pytest.mark.asyncio
    async def test_exhausted_retries_raise_conflict(self, monkeypatch, fake_session):
        fake_db = _ConflictDB("uq_session_events_session_sequence")

        async def always_none(db, session_id, user_id, turn_id):
            return None

        monkeypatch.setattr(svc, "get_session_event_by_turn_id", always_none)

        with pytest.raises(svc.StateConflictError):
            await svc.reserve_session_event(fake_db, "sess-1", 1, "type", "turn-1")
        assert fake_db.flushes == 3

    @pytest.mark.asyncio
    async def test_alternative_conflict_messages_are_recognized(
        self, monkeypatch, fake_session
    ):
        fake_db = _ConflictDB(
            "session_events.session_id, session_events.sequence"
        )
        existing = SimpleNamespace(id="evt-1")
        calls = {"n": 0}

        async def fake_lookup(db, session_id, user_id, turn_id):
            calls["n"] += 1
            return None if calls["n"] == 1 else existing

        monkeypatch.setattr(svc, "get_session_event_by_turn_id", fake_lookup)

        event, created = await svc.reserve_session_event(
            fake_db, "sess-1", 1, "type", "turn-1"
        )

        assert event is existing
        assert created is False


class TestUpdateSessionEvent:
    @pytest.mark.asyncio
    async def test_missing_event_raises_not_found(self, db):
        session = await svc.create_session(db, 1, "ppt")

        with pytest.raises(svc.StateNotFoundError):
            await svc.update_session_event(
                db, session.id, 1, "missing-turn", "done"
            )

    @pytest.mark.asyncio
    async def test_event_disappearing_after_update_raises(self, db, monkeypatch):
        session = await svc.create_session(db, 1, "ppt")
        await svc.append_session_event(db, session.id, 1, "started", "turn-1")

        async def always_none(db, session_id, user_id, turn_id):
            return None

        monkeypatch.setattr(svc, "get_session_event_by_turn_id", always_none)

        with pytest.raises(svc.StateNotFoundError):
            await svc.update_session_event(db, session.id, 1, "turn-1", "done")


class TestCreateTaskIdempotency:
    @pytest.mark.asyncio
    async def test_existing_idempotency_key_returns_task(self, db):
        session = await svc.create_session(db, 1, "ppt")
        first = await svc.create_task(
            db,
            1,
            "ppt_generation",
            session_id=session.id,
            idempotency_key="idem-1",
        )
        second = await svc.create_task(
            db, 1, "ppt_generation", idempotency_key="idem-1"
        )

        assert second.task_id == first.task_id
        assert second.params["idempotency_key"] == "idem-1"

    @pytest.mark.asyncio
    async def test_flush_conflict_raises_state_conflict(self):
        class _TaskDB:
            def __init__(self):
                self.rolled_back = False

            def add(self, obj):
                pass

            async def flush(self):
                raise IntegrityError("stmt", {}, Exception("duplicate"))

            async def rollback(self):
                self.rolled_back = True

        fake_db = _TaskDB()

        with pytest.raises(svc.StateConflictError):
            await svc.create_task(fake_db, 1, "ppt_generation")
        assert fake_db.rolled_back is True

    @pytest.mark.asyncio
    async def test_missing_session_raises_not_found(self, db):
        with pytest.raises(svc.StateNotFoundError):
            await svc.create_task(db, 1, "ppt_generation", session_id="missing")


class TestGetOwnedTask:
    @pytest.mark.asyncio
    async def test_missing_task_raises_not_found(self, db):
        with pytest.raises(svc.StateNotFoundError):
            await svc.get_owned_task(db, "missing", 1)

    @pytest.mark.asyncio
    async def test_foreign_task_raises_ownership(self, db):
        task = await svc.create_task(db, 1, "ppt_generation")
        with pytest.raises(svc.StateOwnershipError):
            await svc.get_owned_task(db, task.task_id, 2)


class TestTransitionTask:
    @pytest.mark.asyncio
    async def test_revision_mismatch_raises_conflict(self, db):
        task = await svc.create_task(db, 1, "ppt_generation")

        with pytest.raises(svc.StateConflictError):
            await svc.transition_task(
                db, task.task_id, 1, "running", expected_revision=99
            )

    @pytest.mark.asyncio
    async def test_terminal_task_rejects_new_status(self, db):
        task = await svc.create_task(db, 1, "ppt_generation")
        await svc.transition_task(db, task.task_id, 1, "success")

        with pytest.raises(svc.StateConflictError):
            await svc.transition_task(db, task.task_id, 1, "failed")

    @pytest.mark.asyncio
    async def test_recovery_allows_leaving_terminal_state(self, db):
        task = await svc.create_task(db, 1, "ppt_generation")
        await svc.transition_task(db, task.task_id, 1, "success")

        recovered = await svc.transition_task(
            db, task.task_id, 1, "running", allow_recovery=True
        )

        assert recovered.status == "running"

    @pytest.mark.asyncio
    async def test_running_sets_started_at_and_progress(self, db):
        task = await svc.create_task(db, 1, "ppt_generation")

        updated = await svc.transition_task(
            db, task.task_id, 1, "running", progress=150, stage="generate"
        )

        assert updated.started_at is not None
        assert updated.progress == 100
        assert updated.progress_message == "generate"

    @pytest.mark.asyncio
    async def test_result_and_error_fields_are_written(self, db):
        task = await svc.create_task(db, 1, "ppt_generation")

        updated = await svc.transition_task(
            db,
            task.task_id,
            1,
            "success",
            result={"path": "a.pptx"},
            error_message="",
        )

        assert updated.result == {"path": "a.pptx"}
        assert updated.result_json == {"path": "a.pptx"}
        assert updated.error_message is None
        assert updated.error_json == {}
        assert updated.completed_at is not None
        assert updated.finished_at == updated.completed_at

    @pytest.mark.asyncio
    async def test_error_message_sets_error_json(self, db):
        task = await svc.create_task(db, 1, "ppt_generation")

        updated = await svc.transition_task(
            db, task.task_id, 1, "failed", error_message="boom"
        )

        assert updated.error_message == "boom"
        assert updated.error_json == {"message": "boom"}


class TestHeartbeatTask:
    @pytest.mark.asyncio
    async def test_heartbeat_updates_worker_and_lease(self, db):
        task = await svc.create_task(db, 1, "ppt_generation")
        lease = datetime.utcnow() + timedelta(minutes=5)

        updated = await svc.heartbeat_task(db, task.task_id, 1, "worker-1", lease)

        assert updated.worker_id == "worker-1"
        assert updated.lease_until == lease

    @pytest.mark.asyncio
    async def test_terminal_task_rejects_heartbeat(self, db):
        task = await svc.create_task(db, 1, "ppt_generation")
        await svc.transition_task(db, task.task_id, 1, "success")

        with pytest.raises(svc.StateConflictError):
            await svc.heartbeat_task(
                db, task.task_id, 1, "worker-1", datetime.utcnow()
            )


class TestCompareTaskSnapshot:
    @pytest.mark.asyncio
    async def test_consistent_snapshot(self, db):
        task = await svc.create_task(db, 1, "ppt_generation")
        await svc.transition_task(db, task.task_id, 1, "running", progress=10)

        result = await svc.compare_task_snapshot(
            db,
            task.task_id,
            1,
            {"status": "running", "progress": 10, "error_message": None},
        )

        assert result["consistent"] is True
        assert result["differences"] == {}

    @pytest.mark.asyncio
    async def test_divergent_snapshot_lists_differences(self, db):
        task = await svc.create_task(db, 1, "ppt_generation")
        await svc.transition_task(db, task.task_id, 1, "running", progress=10)

        result = await svc.compare_task_snapshot(
            db, task.task_id, 1, {"status": "pending", "progress": 10}
        )

        assert result["consistent"] is False
        assert "status" in result["differences"]
        assert "progress" not in result["differences"]


class TestCreateArtifactOwnership:
    @pytest.mark.asyncio
    async def test_missing_task_raises_not_found(self, db):
        with pytest.raises(svc.StateNotFoundError):
            await svc.create_artifact(
                db, 1, "pptx", "uri", task_id="missing"
            )

    @pytest.mark.asyncio
    async def test_missing_session_raises_not_found(self, db):
        task = await svc.create_task(db, 1, "ppt_generation")

        with pytest.raises(svc.StateNotFoundError):
            await svc.create_artifact(
                db, 1, "pptx", "uri", task_id=task.task_id, session_id="missing"
            )

    @pytest.mark.asyncio
    async def test_standalone_artifact_skips_ownership_checks(self, db):
        artifact = await svc.create_artifact(db, 1, "pptx", "uri")

        assert artifact.task_id is None
        assert artifact.session_id is None
        assert artifact.version == 1


class TestLatestSessionEvent:
    @pytest.mark.asyncio
    async def test_filters_by_event_type(self, db):
        session = await svc.create_session(db, 1, "ppt")
        await svc.append_session_event(db, session.id, 1, "started", "turn-1")
        await svc.append_session_event(db, session.id, 1, "progress", "turn-2")
        await svc.append_session_event(db, session.id, 1, "completed", "turn-3")

        latest = await svc.get_latest_session_event(
            db, session.id, 1, event_types=("progress", "completed")
        )

        assert latest.event_type == "completed"

    @pytest.mark.asyncio
    async def test_without_filter_returns_newest(self, db):
        session = await svc.create_session(db, 1, "ppt")
        await svc.append_session_event(db, session.id, 1, "started", "turn-1")
        await svc.append_session_event(db, session.id, 1, "progress", "turn-2")

        latest = await svc.get_latest_session_event(db, session.id, 1)

        assert latest.event_type == "progress"


class TestSaveCheckpointIdempotency:
    @pytest.mark.asyncio
    async def test_existing_checkpoint_is_returned(self, db):
        task = await svc.create_task(db, 1, "ppt_generation")
        first = await svc.save_checkpoint(
            db, task.task_id, 1, 1, "outline", {"a": 1}, "idem-1"
        )
        second = await svc.save_checkpoint(
            db, task.task_id, 1, 2, "other", {"b": 2}, "idem-1"
        )

        assert second.id == first.id
        assert second.step == "outline"
        assert second.state_json == {"a": 1}
