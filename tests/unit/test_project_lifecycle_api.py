from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.ai_agent.lifecycle_endpoints import permanently_delete_project_endpoint
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


async def _seed_project(db, tmp_path: Path, session_id: str = "2_api-reclaim") -> Path:
    project_dir = tmp_path / "2" / "api-reclaim"
    project_dir.mkdir(parents=True)
    (project_dir / "main.py").write_text("print('hi')\n")
    db.add(ProjectSession(
        session_id=session_id,
        user_id="2",
        requirement="hello",
        output_dir="2/api-reclaim",
        status="completed",
        lifecycle_status="active",
    ))
    await db.flush()
    return project_dir


@pytest.mark.asyncio
async def test_delete_endpoint_removes_owned_project(db, tmp_path, monkeypatch):
    from app.api.v1.ai_agent import lifecycle_endpoints

    monkeypatch.setattr(lifecycle_endpoints, "PROJECTS_BASE_DIR", tmp_path)
    project_dir = await _seed_project(db, tmp_path)

    result = await permanently_delete_project_endpoint(
        "2_api-reclaim",
        {"sub": "2"},
        db,
    )

    assert result["status"] == "deleted"
    assert result["session_id"] == "2_api-reclaim"
    assert not project_dir.exists()


@pytest.mark.asyncio
async def test_delete_endpoint_returns_404_for_missing_project(db, tmp_path, monkeypatch):
    from app.api.v1.ai_agent import lifecycle_endpoints

    monkeypatch.setattr(lifecycle_endpoints, "PROJECTS_BASE_DIR", tmp_path)
    with pytest.raises(HTTPException) as error:
        await permanently_delete_project_endpoint("missing", {"sub": "2"}, db)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_endpoint_rejects_foreign_project(db, tmp_path, monkeypatch):
    from app.api.v1.ai_agent import lifecycle_endpoints

    monkeypatch.setattr(lifecycle_endpoints, "PROJECTS_BASE_DIR", tmp_path)
    await _seed_project(db, tmp_path)
    with pytest.raises(HTTPException) as error:
        await permanently_delete_project_endpoint("2_api-reclaim", {"sub": "9"}, db)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_endpoint_rejects_active_generation(db, tmp_path, monkeypatch):
    from app.api.v1.ai_agent import lifecycle_endpoints, orchestrate_endpoints

    monkeypatch.setattr(lifecycle_endpoints, "PROJECTS_BASE_DIR", tmp_path)
    project_dir = await _seed_project(db, tmp_path, "2_busy")

    class _LiveTask:
        def done(self):
            return False

    orchestrate_endpoints._active_tasks["2_busy"] = {"gen_task": _LiveTask()}
    try:
        with pytest.raises(HTTPException) as error:
            await permanently_delete_project_endpoint("2_busy", {"sub": "2"}, db)
        assert error.value.status_code == 409
        assert project_dir.exists()
    finally:
        orchestrate_endpoints._active_tasks.pop("2_busy", None)
