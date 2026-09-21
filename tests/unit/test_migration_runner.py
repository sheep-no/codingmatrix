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


@pytest.mark.asyncio
async def test_runtime_runner_upgrades_existing_tasks_outline_columns(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "legacy-tasks.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.execute(text(
            "CREATE TABLE tasks ("
            "id INTEGER PRIMARY KEY, task_id VARCHAR(64), task_type VARCHAR(50), "
            "status VARCHAR(20), user_id INTEGER)"
        ))
    await engine.dispose()

    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")
    await run_async_migrations()

    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.connect() as connection:
        columns = await connection.execute(text("PRAGMA table_info(tasks)"))
        column_names = {row[1] for row in columns}
    await engine.dispose()

    assert {
        "outline_id",
        "outline_version",
        "quality_mode",
        "quality_report_artifact_id",
    } <= column_names


@pytest.mark.asyncio
async def test_runtime_runner_creates_unique_task_identity_index(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "fresh-index.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")

    await run_async_migrations()

    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.connect() as connection:
        indexes = await connection.execute(text("PRAGMA index_list(tasks)"))
        task_indexes = {row[1]: row for row in indexes}
    await engine.dispose()

    # PRAGMA index_list 返回列：seq, name, unique, origin, partial。
    # 外键指向 tasks.task_id，缺少唯一索引会让 checkpoints/artifacts 的级联约束报
    # "foreign key mismatch"。
    assert "ix_tasks_task_id" in task_indexes
    assert task_indexes["ix_tasks_task_id"][2] == 1


async def _unique_user_id_indexes(database_path: Path) -> set[str]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.connect() as connection:
        indexes = await connection.execute(text("PRAGMA index_list(permission)"))
        found = set()
        for index_row in indexes:
            if not index_row[2]:
                continue
            columns = await connection.execute(
                text(f"PRAGMA index_info('{index_row[1]}')")
            )
            if [row[2] for row in columns] == ["user_id"]:
                found.add(index_row[1])
    await engine.dispose()
    return found


@pytest.mark.asyncio
async def test_runtime_runner_adds_permission_unique_index_to_legacy_table(
    tmp_path, monkeypatch
):
    database_path = Path(tmp_path) / "legacy-permission.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.execute(text(
            "CREATE TABLE permission ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
            "permission_level VARCHAR(20) NOT NULL DEFAULT 'normal')"
        ))
        await connection.execute(text(
            "INSERT INTO permission (user_id, permission_level) VALUES (1, 'normal')"
        ))
    await engine.dispose()

    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")
    await run_async_migrations()
    # 重复执行不应报 "index already exists"
    await run_async_migrations()

    assert await _unique_user_id_indexes(database_path) == {"uq_permission_user_id"}


@pytest.mark.asyncio
async def test_runtime_runner_skips_permission_index_when_duplicates_exist(
    tmp_path, monkeypatch
):
    database_path = Path(tmp_path) / "duplicate-permission.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.execute(text(
            "CREATE TABLE permission ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
            "permission_level VARCHAR(20) NOT NULL DEFAULT 'normal')"
        ))
        await connection.execute(text(
            "INSERT INTO permission (user_id, permission_level) VALUES (7, 'normal'), (7, 'admin')"
        ))
    await engine.dispose()

    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")
    await run_async_migrations()

    # 有重复数据时只告警、不删数据、不建唯一索引
    assert await _unique_user_id_indexes(database_path) == set()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.connect() as connection:
        count = (await connection.execute(text("SELECT COUNT(*) FROM permission"))).scalar()
    await engine.dispose()
    assert count == 2


@pytest.mark.asyncio
async def test_runtime_runner_keeps_fresh_permission_constraint(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "fresh-permission.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")

    await run_async_migrations()
    await run_async_migrations()

    # 新建库由模型约束给出唯一性，重复执行不应再叠加一个同义索引
    assert len(await _unique_user_id_indexes(database_path)) == 1
