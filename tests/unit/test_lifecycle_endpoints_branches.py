"""Branch coverage for app/api/v1/ai_agent/lifecycle_endpoints.py."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.ai_agent import lifecycle_endpoints as endpoints
from app.db.models import ProjectSession
from app.models.base import Base


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed(db, session_id="2_proj", user_id="2", lifecycle_status="active"):
    db.add(
        ProjectSession(
            session_id=session_id,
            user_id=user_id,
            requirement="r",
            output_dir="2/proj",
            status="completed",
            lifecycle_status=lifecycle_status,
        )
    )
    await db.flush()


@pytest.mark.asyncio
async def test_owned_project_rejects_non_numeric_user(db):
    with pytest.raises(Exception) as exc:
        await endpoints._owned_project(db, "2_proj", {"sub": "not-a-number"})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_owned_project_rejects_missing_sub(db):
    with pytest.raises(Exception) as exc:
        await endpoints._owned_project(db, "2_proj", {})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_archive_success(db, monkeypatch):
    await _seed(db)
    project = SimpleNamespace(session_id="2_proj", lifecycle_status="archived")
    monkeypatch.setattr(endpoints, "archive_project", AsyncMock(return_value=project))

    response = await endpoints.archive_project_endpoint("2_proj", {"sub": "2"}, db)

    assert response == {"session_id": "2_proj", "lifecycle_status": "archived"}


@pytest.mark.asyncio
async def test_archive_conflict(db, monkeypatch):
    await _seed(db)
    monkeypatch.setattr(
        endpoints, "archive_project", AsyncMock(side_effect=ValueError("busy"))
    )

    with pytest.raises(Exception) as exc:
        await endpoints.archive_project_endpoint("2_proj", {"sub": "2"}, db)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_restore_success(db, monkeypatch):
    await _seed(db, lifecycle_status="archived")
    project = SimpleNamespace(session_id="2_proj", lifecycle_status="active")
    monkeypatch.setattr(endpoints, "restore_project", AsyncMock(return_value=project))

    response = await endpoints.restore_project_endpoint("2_proj", {"sub": "2"}, db)

    assert response == {"session_id": "2_proj", "lifecycle_status": "active"}


@pytest.mark.asyncio
async def test_restore_conflict(db, monkeypatch):
    await _seed(db, lifecycle_status="archived")
    monkeypatch.setattr(
        endpoints, "restore_project", AsyncMock(side_effect=ValueError("bad"))
    )

    with pytest.raises(Exception) as exc:
        await endpoints.restore_project_endpoint("2_proj", {"sub": "2"}, db)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_conflict_on_os_error(db, monkeypatch, tmp_path):
    await _seed(db)
    monkeypatch.setattr(endpoints, "PROJECTS_BASE_DIR", tmp_path)
    monkeypatch.setattr(
        endpoints,
        "permanently_delete_project",
        AsyncMock(side_effect=OSError("io")),
    )

    with pytest.raises(Exception) as exc:
        await endpoints.permanently_delete_project_endpoint("2_proj", {"sub": "2"}, db)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_pin_and_unpin(db, monkeypatch):
    await _seed(db)
    pinned = SimpleNamespace(session_id="2_proj", pinned=True)
    unpinned = SimpleNamespace(session_id="2_proj", pinned=False)
    calls = []

    async def _set(_db, session_id, value):
        calls.append(value)
        return pinned if value else unpinned

    monkeypatch.setattr(endpoints, "set_project_pinned", _set)

    first = await endpoints.pin_project_endpoint("2_proj", {"sub": "2"}, db)
    second = await endpoints.unpin_project_endpoint("2_proj", {"sub": "2"}, db)

    assert first["pinned"] is True
    assert second["pinned"] is False
    assert calls == [True, False]


@pytest.mark.asyncio
async def test_owned_project_returns_404(db):
    with pytest.raises(Exception) as exc:
        await endpoints._owned_project(db, "missing", {"sub": "2"})
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_success(db, monkeypatch, tmp_path):
    await _seed(db)
    monkeypatch.setattr(endpoints, "PROJECTS_BASE_DIR", tmp_path)
    monkeypatch.setattr(
        endpoints,
        "permanently_delete_project",
        AsyncMock(return_value={"status": "deleted", "session_id": "2_proj"}),
    )

    result = await endpoints.permanently_delete_project_endpoint("2_proj", {"sub": "2"}, db)

    assert result["status"] == "deleted"
