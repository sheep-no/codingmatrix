"""SQLite 主库连接配置回归（DB1/DB3）。

默认部署使用 SQLite：外键约束默认关闭、默认 busy_timeout=0 且非 WAL，
导致级联删除失效、并发写立即 database is locked。
"""

import os

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


def _conftest_module():
    try:
        import tests.conftest as conftest_mod
    except ImportError:  # pragma: no cover - 取决于 conftest 的导入名
        import conftest as conftest_mod
    return conftest_mod


def test_test_session_targets_dedicated_database():
    """回归：测试会话必须连独立测试库，否则 test_db_setup 的 drop_all 会清空开发库 app.db。"""
    if os.environ.get("TEST_DATABASE_URL"):
        return
    db_name = os.path.basename(settings.DATABASE_URL.split("///")[-1])
    assert "test" in os.path.splitext(db_name)[0].lower(), settings.DATABASE_URL


def test_drop_all_guard_rejects_non_test_database(monkeypatch):
    """回归：非测试库上必须拒绝执行清表 fixture，避免误删真实数据。"""
    conftest_mod = _conftest_module()
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setattr(
        conftest_mod.settings, "DATABASE_URL", "sqlite+aiosqlite:///./app.db"
    )
    with pytest.raises(RuntimeError, match="非测试库"):
        conftest_mod._assert_dedicated_test_database()


def test_drop_all_guard_allows_memory_database(monkeypatch):
    """内存库天然隔离，守卫应放行。"""
    conftest_mod = _conftest_module()
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setattr(
        conftest_mod.settings, "DATABASE_URL", "sqlite+aiosqlite:///:memory:"
    )
    conftest_mod._assert_dedicated_test_database()
