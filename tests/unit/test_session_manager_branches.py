import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent import session_manager as sm


def _manager(tmp_path, db_session_factory=None):
    return sm.SessionManager(
        tmp_path / "sessions", db_session_factory=db_session_factory
    )


class _FakeResult:
    def __init__(self, session):
        self._session = session

    def scalar_one_or_none(self):
        return self._session


class _FakeDB:
    def __init__(self, session):
        self.session = session
        self.commits = 0

    async def execute(self, *_a, **_k):
        return _FakeResult(self.session)

    async def commit(self):
        self.commits += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


def _fake_factory(session):
    def factory():
        return _FakeDB(session)

    return factory


@pytest.mark.asyncio
async def test_sync_to_db_without_factory_is_noop(tmp_path):
    manager = _manager(tmp_path)

    await manager._sync_to_db("s", "running")


@pytest.mark.asyncio
async def test_sync_to_db_updates_existing_session(tmp_path):
    db_session = SimpleNamespace(
        status=None,
        last_activity_at=None,
        files_generated=0,
        files_total=0,
        error_message=None,
        completed_at=None,
    )
    db = _FakeDB(db_session)
    manager = _manager(tmp_path, db_session_factory=lambda: db)

    await manager._sync_to_db(
        "s", "completed", files_generated=3, files_total=5, error_message="e"
    )

    assert db_session.status == "completed"
    assert db_session.files_generated == 3
    assert db_session.files_total == 5
    assert db_session.error_message == "e"
    assert db_session.completed_at is not None
    assert db.commits == 1


@pytest.mark.asyncio
async def test_sync_to_db_warns_when_session_missing(tmp_path, monkeypatch):
    manager = _manager(tmp_path, db_session_factory=_fake_factory(None))
    warnings = []
    monkeypatch.setattr(
        sm, "logger", SimpleNamespace(warning=warnings.append, debug=lambda *a, **k: None, error=lambda *a, **k: None, info=lambda *a, **k: None)
    )

    await manager._sync_to_db("missing", "running")

    assert warnings


@pytest.mark.asyncio
async def test_sync_to_db_swallows_exceptions(tmp_path, monkeypatch):
    def boom():
        raise RuntimeError("db down")

    manager = _manager(tmp_path, db_session_factory=boom)
    warnings = []
    monkeypatch.setattr(
        sm, "logger", SimpleNamespace(warning=warnings.append, debug=lambda *a, **k: None, error=lambda *a, **k: None, info=lambda *a, **k: None)
    )

    await manager._sync_to_db("s", "running")

    assert warnings


@pytest.mark.asyncio
async def test_sync_to_db_running_skips_optional_fields(tmp_path):
    db_session = SimpleNamespace(
        status=None,
        last_activity_at=None,
        files_generated=7,
        files_total=9,
        error_message=None,
        completed_at=None,
    )
    db = _FakeDB(db_session)
    manager = _manager(tmp_path, db_session_factory=lambda: db)

    await manager._sync_to_db("s", "running")

    assert db_session.status == "running"
    assert db_session.files_generated == 7
    assert db_session.files_total == 9
    assert db_session.completed_at is None
    assert db.commits == 1


@pytest.mark.asyncio
async def test_create_session_skips_empty_file_paths(tmp_path):
    manager = _manager(tmp_path)
    state = await manager.create_session(
        "req", str(tmp_path / "out"), file_plan=[{"path": ""}, {"name": "x"}]
    )

    assert state.file_statuses == {}
    assert state.files_total == 2


@pytest.mark.asyncio
async def test_create_session_with_explicit_id(tmp_path):
    manager = _manager(tmp_path)

    state = await manager.create_session(
        "req", str(tmp_path / "out"), session_id="explicit-id"
    )

    assert state.session_id == "explicit-id"


@pytest.mark.asyncio
async def test_resume_session_returns_cached(tmp_path):
    manager = _manager(tmp_path)
    state = await manager.create_session("req", str(tmp_path / "out"))

    assert await manager.resume_session(state.session_id) is state


@pytest.mark.asyncio
async def test_resume_session_missing_file(tmp_path):
    manager = _manager(tmp_path)

    assert await manager.resume_session("nope") is None


@pytest.mark.asyncio
async def test_resume_session_expired(tmp_path):
    manager = _manager(tmp_path)
    state = await manager.create_session("req", str(tmp_path / "out"))
    old = (datetime.now() - timedelta(seconds=sm.SESSION_TTL_SECONDS + 10)).isoformat()
    state.updated_at = old
    await manager._save_session(state)
    manager._active_sessions.clear()

    assert await manager.resume_session(state.session_id) is None


@pytest.mark.asyncio
async def test_resume_session_invalid_timestamp(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    state = await manager.create_session("req", str(tmp_path / "out"))
    state.updated_at = "not-a-date"
    await manager._save_session(state)
    manager._active_sessions.clear()

    assert await manager.resume_session(state.session_id) is None


@pytest.mark.asyncio
async def test_resume_session_returns_existing_after_lock(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    state = await manager.create_session("req", str(tmp_path / "out"))
    manager._active_sessions.clear()

    original_get = manager._get_session_lock

    def racing_lock(session_id):
        # Simulate another coroutine restoring the state between the double-check.
        manager._active_sessions[session_id] = state
        return original_get(session_id)

    monkeypatch.setattr(manager, "_get_session_lock", racing_lock)

    resumed = await manager.resume_session(state.session_id)

    assert resumed is state


@pytest.mark.asyncio
async def test_resume_session_read_failure(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    state = await manager.create_session("req", str(tmp_path / "out"))
    manager._active_sessions.clear()

    def boom(*_a, **_k):
        raise OSError("corrupt")

    monkeypatch.setattr(manager, "_read_session_json", boom)

    assert await manager.resume_session(state.session_id) is None


@pytest.mark.asyncio
async def test_update_file_status_missing_session(tmp_path):
    manager = _manager(tmp_path)

    await manager.update_file_status("nope", "main.py", "completed")


@pytest.mark.asyncio
async def test_update_file_status_creates_status_and_computes_hash(tmp_path):
    manager = _manager(tmp_path)
    state = await manager.create_session("req", str(tmp_path / "out"))

    await manager.update_file_status(state.session_id, "new.py", "completed", content="x", error="e")

    fs = state.file_statuses["new.py"]
    assert fs.status == "completed"
    assert fs.error == "e"
    assert fs.content_hash
    assert state.files_generated == 1


@pytest.mark.asyncio
async def test_update_file_status_non_completed_does_not_count(tmp_path):
    manager = _manager(tmp_path)
    state = await manager.create_session(
        "req", str(tmp_path / "out"), file_plan=[{"path": "a.py"}]
    )

    await manager.update_file_status(state.session_id, "a.py", "generating")

    assert state.files_generated == 0


@pytest.mark.asyncio
async def test_pause_and_resume_approved(tmp_path):
    manager = _manager(tmp_path)
    state = await manager.create_session("req", str(tmp_path / "out"))

    await manager.pause_session(state.session_id, "reason", "main.py")
    assert state.status == sm.SessionStatus.PAUSED.value
    assert state.pause_file == "main.py"

    await manager.resume_from_pause(state.session_id, approved=True)
    assert state.status == sm.SessionStatus.RUNNING.value
    assert state.pause_reason == ""


@pytest.mark.asyncio
async def test_resume_from_pause_rejected_marks_skipped(tmp_path):
    manager = _manager(tmp_path)
    state = await manager.create_session(
        "req", str(tmp_path / "out"), file_plan=[{"path": "a.py"}]
    )
    await manager.pause_session(state.session_id, "reason", "a.py")

    await manager.resume_from_pause(state.session_id, approved=False)

    assert state.file_statuses["a.py"].status == "skipped"


@pytest.mark.asyncio
async def test_resume_from_pause_rejected_missing_pause_file(tmp_path):
    manager = _manager(tmp_path)
    state = await manager.create_session("req", str(tmp_path / "out"))
    await manager.pause_session(state.session_id, "reason", "missing.py")

    await manager.resume_from_pause(state.session_id, approved=False)

    assert state.status == sm.SessionStatus.RUNNING.value


@pytest.mark.asyncio
async def test_pause_and_resume_missing_session_noop(tmp_path):
    manager = _manager(tmp_path)

    await manager.pause_session("nope", "reason")
    await manager.resume_from_pause("nope")


@pytest.mark.asyncio
async def test_complete_session_with_errors_and_counts(tmp_path):
    manager = _manager(tmp_path)
    state = await manager.create_session("req", str(tmp_path / "out"))

    await manager.complete_session(
        state.session_id, errors=["boom"], files_generated=2, files_total=4
    )

    assert state.status == sm.SessionStatus.FAILED.value
    assert state.errors == ["boom"]
    assert state.files_generated == 2
    assert state.files_total == 4
    assert state.completed_at


@pytest.mark.asyncio
async def test_complete_session_missing_noop(tmp_path):
    manager = _manager(tmp_path)

    await manager.complete_session("nope")


@pytest.mark.asyncio
async def test_complete_session_without_overrides(tmp_path):
    manager = _manager(tmp_path)
    state = await manager.create_session("req", str(tmp_path / "out"))
    state.files_generated = 4
    state.files_total = 6

    await manager.complete_session(state.session_id)

    assert state.status == sm.SessionStatus.COMPLETED.value
    assert state.files_generated == 4
    assert state.files_total == 6


@pytest.mark.asyncio
async def test_cancel_session_missing_syncs_db(tmp_path):
    calls = []
    manager = _manager(tmp_path, db_session_factory=_fake_factory(None))

    async def fake_sync(*args, **kwargs):
        calls.append(args)

    manager._sync_to_db = fake_sync

    await manager.cancel_session("missing")

    assert calls


@pytest.mark.asyncio
async def test_cancel_session_updates_state(tmp_path):
    manager = _manager(tmp_path)
    state = await manager.create_session("req", str(tmp_path / "out"))

    await manager.cancel_session(state.session_id)

    assert state.status == sm.SessionStatus.CANCELLED.value
    assert state.completed_at


@pytest.mark.asyncio
async def test_cleanup_expired_removes_files_and_marks_db(tmp_path):
    db_session = SimpleNamespace(status="running", error_message=None, completed_at=None)
    db = _FakeDB(db_session)
    manager = _manager(tmp_path, db_session_factory=lambda: db)
    state = await manager.create_session("req", str(tmp_path / "out"))
    state.updated_at = (datetime.now() - timedelta(seconds=sm.SESSION_TTL_SECONDS + 10)).isoformat()
    await manager._save_session(state)
    session_file = manager._session_file(state.session_id)
    assert session_file.exists()

    removed = await manager.cleanup_expired()

    assert removed == 1
    assert not session_file.exists()
    assert db_session.status == "expired"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_cleanup_expired_invalid_timestamp_removed(tmp_path):
    manager = _manager(tmp_path)
    state = await manager.create_session("req", str(tmp_path / "out"))
    state.updated_at = "bad"
    await manager._save_session(state)

    removed = await manager.cleanup_expired()

    assert removed == 1


@pytest.mark.asyncio
async def test_cleanup_expired_db_failure_swallowed(tmp_path, monkeypatch):
    manager = _manager(tmp_path)

    def boom():
        raise RuntimeError("db down")

    manager._db_session_factory = boom
    state = await manager.create_session("req", str(tmp_path / "out"))
    state.updated_at = (datetime.now() - timedelta(seconds=sm.SESSION_TTL_SECONDS + 10)).isoformat()
    await manager._save_session(state)
    warnings = []
    monkeypatch.setattr(
        sm, "logger", SimpleNamespace(warning=warnings.append, debug=lambda *a, **k: None, error=lambda *a, **k: None, info=lambda *a, **k: None)
    )

    removed = await manager.cleanup_expired()

    assert removed == 1
    assert warnings


@pytest.mark.asyncio
async def test_cleanup_expired_skips_missing_file_and_non_running_db(tmp_path):
    db_session = SimpleNamespace(status="completed", error_message=None, completed_at=None)
    db = _FakeDB(db_session)
    manager = _manager(tmp_path, db_session_factory=lambda: db)
    state = await manager.create_session("req", str(tmp_path / "out"))
    state.updated_at = (datetime.now() - timedelta(seconds=sm.SESSION_TTL_SECONDS + 10)).isoformat()
    await manager._save_session(state)
    manager._session_file(state.session_id).unlink()

    removed = await manager.cleanup_expired()

    assert removed == 1
    assert db_session.status == "completed"
    assert db.commits == 0


@pytest.mark.asyncio
async def test_cleanup_if_needed_evicts_non_running(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    monkeypatch.setattr(sm, "MAX_ACTIVE_SESSIONS", 1)
    first = await manager.create_session("a", str(tmp_path / "out1"))
    first.status = sm.SessionStatus.COMPLETED.value
    second = await manager.create_session("b", str(tmp_path / "out2"))

    await manager.cleanup_if_needed()

    assert first.session_id not in manager._active_sessions
    assert second.session_id in manager._active_sessions


@pytest.mark.asyncio
async def test_cleanup_if_needed_stops_after_expired_cleanup(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    monkeypatch.setattr(sm, "MAX_ACTIVE_SESSIONS", 2)
    stale = []
    for index in range(2):
        state = await manager.create_session("old", str(tmp_path / f"old{index}"))
        state.updated_at = (
            datetime.now() - timedelta(seconds=sm.SESSION_TTL_SECONDS + 10)
        ).isoformat()
        await manager._save_session(state)
        stale.append(state)
    active = await manager.create_session("new", str(tmp_path / "new"))

    await manager.cleanup_if_needed()

    assert active.session_id in manager._active_sessions
    assert all(state.session_id not in manager._active_sessions for state in stale)


@pytest.mark.asyncio
async def test_cleanup_if_needed_noop_under_limit(tmp_path):
    manager = _manager(tmp_path)
    state = await manager.create_session("a", str(tmp_path / "out"))

    await manager.cleanup_if_needed()

    assert state.session_id in manager._active_sessions


@pytest.mark.asyncio
async def test_get_session_status_missing(tmp_path):
    manager = _manager(tmp_path)

    assert await manager.get_session_status("nope") is None


@pytest.mark.asyncio
async def test_detect_incremental_missing_session(tmp_path):
    manager = _manager(tmp_path)

    with pytest.raises(ValueError, match="会话不存在"):
        await manager.detect_incremental_changes("nope", "req", tmp_path)


@pytest.mark.asyncio
async def test_detect_incremental_changed_and_unchanged(tmp_path):
    manager = _manager(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    state = await manager.create_session(
        "req", str(out), file_plan=[{"path": "a.py"}, {"path": "b.py"}, {"path": "c.py"}, {"path": ""}]
    )
    (out / "a.py").write_text("same", encoding="utf-8")
    (out / "b.py").write_text("changed", encoding="utf-8")
    fs = state.file_statuses["a.py"]
    fs.status = "completed"
    fs.content_hash = sm.SessionManager._compute_hash("same")
    await manager._save_session(state)

    result = await manager.detect_incremental_changes(state.session_id, "req", out)

    assert "a.py" in result["unchanged_files"]
    assert "b.py" in result["changed_files"]
    assert "c.py" in result["changed_files"]


@pytest.mark.asyncio
async def test_detect_incremental_requirement_change_forces_changed(tmp_path):
    manager = _manager(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    state = await manager.create_session(
        "old req", str(out), file_plan=[{"path": "a.py"}]
    )
    (out / "a.py").write_text("same", encoding="utf-8")
    fs = state.file_statuses["a.py"]
    fs.status = "completed"
    fs.content_hash = sm.SessionManager._compute_hash("same")
    await manager._save_session(state)

    result = await manager.detect_incremental_changes(state.session_id, "new req", out)

    assert result["changed_files"] == ["a.py"]
    assert result["state"].requirement == "new req"


@pytest.mark.asyncio
async def test_detect_incremental_embedding_similarity_low_marks_changed(tmp_path):
    manager = _manager(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    state = await manager.create_session(
        "req", str(out), file_plan=[{"path": "a.py"}]
    )
    (out / "a.py").write_text("v2", encoding="utf-8")
    fs = state.file_statuses["a.py"]
    fs.status = "completed"
    fs.content_hash = "stale"
    fs.content_embedding = [1.0, 0.0]
    await manager._save_session(state)

    result = await manager.detect_incremental_changes(
        state.session_id, "req", out, file_embeddings={"a.py": [0.0, 1.0]}
    )

    assert result["changed_files"] == ["a.py"]


def test_get_file_plan_for_incremental_filters(tmp_path):
    manager = _manager(tmp_path)
    state = sm.SessionState(
        session_id="s",
        requirement="r",
        file_plan=[{"path": "a.py"}, {"path": "b.py"}],
        is_incremental=True,
        changed_files=["b.py"],
    )

    assert manager.get_file_plan_for_incremental(state) == [{"path": "b.py"}]

    state.is_incremental = False
    assert manager.get_file_plan_for_incremental(state) == state.file_plan


def test_compute_hash_and_similarity():
    assert sm.SessionManager._compute_hash("x") == sm.SessionManager._compute_hash("x")
    assert sm.SessionManager._compute_embedding_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_get_session_lock_reuses_lock(tmp_path):
    manager = _manager(tmp_path)

    assert manager._get_session_lock("s") is manager._get_session_lock("s")


@pytest.mark.asyncio
async def test_save_session_logs_and_reraises(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    state = await manager.create_session("req", str(tmp_path / "out"))
    errors = []
    monkeypatch.setattr(
        sm, "logger", SimpleNamespace(
            error=errors.append,
            warning=lambda *a, **k: None,
            debug=lambda *a, **k: None,
            info=lambda *a, **k: None,
        )
    )

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(manager, "_write_session_json", boom)

    with pytest.raises(OSError, match="disk full"):
        await manager._save_session(state)
    assert errors


def test_session_state_from_dict_handles_file_statuses():
    payload = {
        "session_id": "s",
        "requirement": "r",
        "file_statuses": {
            "a.py": {"path": "a.py", "status": "completed"},
            "b.py": "invalid",
        },
    }

    state = sm.SessionState.from_dict(payload)

    assert isinstance(state.file_statuses["a.py"], sm.FileStatus)
    assert state.file_statuses["b.py"] == "invalid"
    assert state.approval_queue is not None


def test_session_state_to_dict_excludes_private_fields():
    state = sm.SessionState(session_id="s", requirement="r")

    data = state.to_dict()

    assert "_approval_queue" not in data
    assert data["session_id"] == "s"
