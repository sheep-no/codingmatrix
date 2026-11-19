import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.ai_agent import helpers, orchestrate_endpoints
from app.db.models import ProjectSession
from app.db.session_recovery import INTERRUPTED_SESSION_MESSAGE, reconcile_interrupted_sessions
from app.models.unified_state import Session as UnifiedSession


def _db_returning(sessions):
    result = MagicMock()
    result.scalars.return_value.all.return_value = sessions
    db = AsyncMock()
    db.execute.return_value = result
    return db


@pytest.mark.asyncio
async def test_reconcile_interrupted_sessions_marks_running_failed_and_keeps_files():
    session = ProjectSession(
        session_id="restarted",
        user_id=1,
        requirement="build",
        output_dir="1/restarted",
        status="running",
    )
    db = _db_returning([session])

    count = await reconcile_interrupted_sessions(db)

    assert count == 1
    assert session.status == "failed"
    assert session.error_message == INTERRUPTED_SESSION_MESSAGE
    assert session.completed_at is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconcile_interrupted_sessions_noop_when_none_running():
    db = _db_returning([])

    assert await reconcile_interrupted_sessions(db) == 0
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconcile_marks_stale_unified_agent_sessions_failed(
    test_db, test_user
):
    agent_session = UnifiedSession(
        id="unified-agent",
        user_id=test_user.id,
        module="agent",
        external_id="orphan",
        status="active",
    )
    aicloud_session = UnifiedSession(
        id="unified-aicloud",
        user_id=test_user.id,
        module="aicloud",
        external_id="chat",
        status="active",
    )
    test_db.add_all([agent_session, aicloud_session])
    await test_db.commit()

    assert await reconcile_interrupted_sessions(test_db) == 0

    await test_db.refresh(agent_session)
    await test_db.refresh(aicloud_session)
    assert agent_session.status == "failed"
    assert aicloud_session.status == "active"


@pytest.mark.asyncio
async def test_recent_zombie_preserves_generated_files(monkeypatch):
    session = ProjectSession(
        session_id="crashed",
        user_id=1,
        requirement="build",
        output_dir="1/crashed",
        status="running",
        last_activity_at=datetime.now(timezone.utc),
    )
    sm = SimpleNamespace(_get_state=AsyncMock(return_value=None))
    cleanup = MagicMock()
    monkeypatch.setattr(helpers, "get_session_manager", AsyncMock(return_value=sm))
    monkeypatch.setattr(helpers, "cleanup_session_files", cleanup)

    count = await helpers._detect_and_clean_zombie_sessions(
        _db_returning([session]), "1"
    )

    assert count == 1
    assert session.status == "failed"
    assert "已生成文件保留" in session.error_message
    cleanup.assert_not_called()


@pytest.mark.asyncio
async def test_expired_zombie_still_reclaims_disk(monkeypatch):
    from datetime import timedelta

    session = ProjectSession(
        session_id="expired",
        user_id=1,
        requirement="build",
        output_dir="1/expired",
        status="running",
        last_activity_at=datetime.now(timezone.utc) - timedelta(days=30),
    )
    sm = SimpleNamespace(_get_state=AsyncMock(return_value=object()))
    cleanup = MagicMock()
    monkeypatch.setattr(helpers, "get_session_manager", AsyncMock(return_value=sm))
    monkeypatch.setattr(helpers, "cleanup_session_files", cleanup)

    assert await helpers._detect_and_clean_zombie_sessions(
        _db_returning([session]), "1"
    ) == 1
    cleanup.assert_called_once_with("1/expired")


@pytest.mark.asyncio
async def test_abandoned_background_generation_stops_after_grace(monkeypatch):
    started = asyncio.Event()

    async def never_finishes():
        started.set()
        await asyncio.sleep(3600)

    gen_task = asyncio.create_task(never_finishes())
    await started.wait()
    cancel_event = asyncio.Event()
    orchestrate_endpoints._active_tasks["s"] = {
        "gen_task": gen_task,
        "cancel_event": cancel_event,
        "connected": False,
    }
    sm = SimpleNamespace(cancel_session=AsyncMock())
    monkeypatch.setattr(
        orchestrate_endpoints, "BACKGROUND_DISCONNECT_GRACE_SECONDS", 0
    )
    monkeypatch.setattr(
        orchestrate_endpoints, "get_session_manager", AsyncMock(return_value=sm)
    )

    try:
        await orchestrate_endpoints._abandon_background_generation("s", gen_task)
        assert gen_task.cancelled()
        assert cancel_event.is_set()
        sm.cancel_session.assert_awaited_once_with("s")
    finally:
        orchestrate_endpoints._active_tasks.pop("s", None)
        if not gen_task.done():
            gen_task.cancel()
        await asyncio.gather(gen_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_abandon_keeps_task_when_client_reconnected(monkeypatch):
    async def still_running():
        await asyncio.sleep(3600)

    gen_task = asyncio.create_task(still_running())
    orchestrate_endpoints._active_tasks["s"] = {
        "gen_task": gen_task,
        "cancel_event": asyncio.Event(),
        "connected": True,
    }
    sm = SimpleNamespace(cancel_session=AsyncMock())
    monkeypatch.setattr(
        orchestrate_endpoints, "BACKGROUND_DISCONNECT_GRACE_SECONDS", 0
    )
    monkeypatch.setattr(
        orchestrate_endpoints, "get_session_manager", AsyncMock(return_value=sm)
    )

    try:
        await orchestrate_endpoints._abandon_background_generation("s", gen_task)
        assert not gen_task.done()
        sm.cancel_session.assert_not_awaited()
    finally:
        orchestrate_endpoints._active_tasks.pop("s", None)
        gen_task.cancel()
        await asyncio.gather(gen_task, return_exceptions=True)
