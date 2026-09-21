"""KOL1/KOL2：用户可控值必须按字面量做子串匹配，不能当 LIKE 通配符。

归属校验与缓存命中都用 `contains(value)`，未转义时 `%`/`_` 会放宽匹配。
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1.kolors_api import _literal_contains
from app.models.file import File


@pytest.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(File.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add(File(
            filename="a.png",
            file_path="uploads/20260821/a.png",
            file_size=10,
            user_id=1,
        ))
        await db.commit()
        yield db
    await engine.dispose()


async def _paths_matching(session, value):
    result = await session.execute(select(File.file_path).where(_literal_contains(File.file_path, value)))
    return result.scalars().all()


@pytest.mark.asyncio
async def test_percent_is_literal_not_wildcard(session):
    """`%` 作为字面量不应命中任何行（未转义时会匹配全部）。"""
    assert await _paths_matching(session, "%") == []


@pytest.mark.asyncio
async def test_underscore_is_literal_not_wildcard(session):
    """`_` 不再匹配任意单字符。"""
    assert await _paths_matching(session, "a_.png") == []


@pytest.mark.asyncio
async def test_plain_substring_still_matches(session):
    """普通路径片段照常命中，转义不影响合法用法。"""
    assert await _paths_matching(session, "a.png") == ["uploads/20260821/a.png"]
    assert await _paths_matching(session, "20260821") == ["uploads/20260821/a.png"]
