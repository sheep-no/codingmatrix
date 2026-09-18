"""SQLite 主库连接配置回归（DB1/DB3）。

默认部署使用 SQLite：外键约束默认关闭、默认 busy_timeout=0 且非 WAL，
导致级联删除失效、并发写立即 database is locked。
"""

import pytest
from sqlalchemy import text

from app.db import database as database_mod
from app.core.config import settings

pytestmark = pytest.mark.skipif(
    not settings.DATABASE_URL.startswith("sqlite"), reason="仅验证 SQLite 主库配置"
)


@pytest.mark.asyncio
async def test_foreign_keys_enabled_per_connection():
    async with database_mod.engine.connect() as conn:
        value = (await conn.execute(text("PRAGMA foreign_keys"))).scalar()
    assert value == 1


@pytest.mark.asyncio
async def test_wal_and_busy_timeout_enabled():
    async with database_mod.engine.connect() as conn:
        journal_mode = (await conn.execute(text("PRAGMA journal_mode"))).scalar()
        busy_timeout = (await conn.execute(text("PRAGMA busy_timeout"))).scalar()
    assert str(journal_mode).lower() == "wal"
    assert busy_timeout >= 30000
