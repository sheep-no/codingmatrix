"""真实 MySQL 运行时集成测试。

默认跳过；在 CI 的 mysql-integration job 中通过 ``MYSQL_TEST_URL`` 启用。
覆盖启动迁移、迁移命名锁与会话 ID 命名锁，避免仅靠 fake DB 验证。
"""
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("MYSQL_TEST_URL"),
        reason="需要 MYSQL_TEST_URL 指向可用的 MySQL 8.x 实例",
    ),
]


def _mysql_url() -> str:
    return os.environ["MYSQL_TEST_URL"]


@pytest.fixture
async def mysql_engine():
    engine = create_async_engine(_mysql_url())
    try:
        yield engine
    finally:
        await engine.dispose()


async def test_run_async_migrations_creates_all_tables(monkeypatch):
    from app.core.config import settings
    from migrations import runner

    monkeypatch.setattr(settings, "DATABASE_URL", _mysql_url())
    await runner.run_async_migrations()

    engine = create_async_engine(_mysql_url())
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = DATABASE()"
                )
            )
            existing = {row[0] for row in result}
    finally:
        await engine.dispose()

    assert set(runner.Base.metadata.tables).issubset(existing)
    assert {"tasks", "history", "sessions"}.issubset(existing)


async def test_run_async_migrations_is_idempotent(monkeypatch):
    from app.core.config import settings
    from migrations import runner

    monkeypatch.setattr(settings, "DATABASE_URL", _mysql_url())
    await runner.run_async_migrations()
    await runner.run_async_migrations()


async def test_mysql_migration_lock_is_exclusive(mysql_engine):
    from migrations.runner import (
        MYSQL_MIGRATION_LOCK,
        _acquire_mysql_migration_lock,
        _release_mysql_migration_lock,
    )

    holder = await mysql_engine.connect()
    contender = await mysql_engine.connect()
    try:
        await _acquire_mysql_migration_lock(holder)
        blocked = await contender.execute(
            text("SELECT GET_LOCK(:name, 0)"), {"name": MYSQL_MIGRATION_LOCK}
        )
        assert blocked.scalar() == 0

        await _release_mysql_migration_lock(holder)
        acquired = await contender.execute(
            text("SELECT GET_LOCK(:name, 0)"), {"name": MYSQL_MIGRATION_LOCK}
        )
        assert acquired.scalar() == 1
    finally:
        await contender.execute(
            text("SELECT RELEASE_LOCK(:name)"), {"name": MYSQL_MIGRATION_LOCK}
        )
        await holder.close()
        await contender.close()


async def test_conversation_id_lock_uses_mysql_named_lock(mysql_engine):
    from app.db.add_history import (
        _acquire_conversation_id_lock,
        _database_dialect,
        _release_conversation_id_lock,
    )

    session_factory = async_sessionmaker(mysql_engine, expire_on_commit=False)
    async with session_factory() as db:
        assert _database_dialect(db) == "mysql"
        lock_conn = await _acquire_conversation_id_lock(db, user_id=424242)
        assert lock_conn is not None
        try:
            async with mysql_engine.connect() as other:
                result = await other.execute(
                    text("SELECT GET_LOCK(:name, 0)"),
                    {"name": "conversation_id:424242"},
                )
                assert result.scalar() == 0
        finally:
            await _release_conversation_id_lock(lock_conn, user_id=424242)
