from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from migrations.runner import run_async_migrations


@pytest.mark.asyncio
async def test_runtime_runner_upgrades_existing_project_sessions(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "legacy.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.execute(text(
            "CREATE TABLE project_sessions ("
            "id INTEGER PRIMARY KEY, session_id VARCHAR(100), user_id VARCHAR(100), "
            "requirement TEXT, output_dir VARCHAR(500), status VARCHAR(50))"
        ))
    await engine.dispose()

    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")
    await run_async_migrations()
    await run_async_migrations()

    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.connect() as connection:
        columns = await connection.execute(text("PRAGMA table_info(project_sessions)"))
        column_names = {row[1] for row in columns}
        indexes = await connection.execute(text("PRAGMA index_list(project_sessions)"))
        index_names = {row[1] for row in indexes}
    await engine.dispose()

    assert {
        "lifecycle_status",
        "retention_class",
        "pinned",
        "archived_at",
        "purge_after",
    } <= column_names
    assert "ix_project_sessions_lifecycle_status" in index_names
