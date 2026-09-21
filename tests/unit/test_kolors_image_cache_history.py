"""KOL4：图像缓存写 History 时复用按用户加锁的 conversation_id 生成。

原实现自行 `select(func.max(conversation_id)) + 1`，与并发新会话/并发缓存
写入会读到同一 max 而撞号（DB6 家族）。
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1.kolors_api import cache_image_to_history, get_cached_image
from app.models.history import History


@pytest.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(History.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


@pytest.mark.asyncio
async def test_cache_then_lookup_roundtrip(session):
    await cache_image_to_history(session, 1, None, "a cat", "uploads/cat.png", 7)

    assert await get_cached_image(session, 1, "a cat", 7, None) == "uploads/cat.png"
    assert await get_cached_image(session, 1, "a dog", 7, None) is None
    assert await get_cached_image(session, 2, "a cat", 7, None) is None


@pytest.mark.asyncio
async def test_none_conversation_id_allocates_distinct_ids(session):
    await cache_image_to_history(session, 1, None, "one", "uploads/1.png", 1)
    await cache_image_to_history(session, 1, None, "two", "uploads/2.png", 2)

    result = await session.execute(select(History.conversation_id).order_by(History.id))
    ids = result.scalars().all()
    assert len(ids) == 2
    assert ids[0] != ids[1]


@pytest.mark.asyncio
async def test_provided_conversation_id_is_reused(session):
    await cache_image_to_history(session, 1, 5, "one", "uploads/1.png", 1)
    await cache_image_to_history(session, 1, 5, "two", "uploads/2.png", 2)

    result = await session.execute(select(History.conversation_id).order_by(History.id))
    assert result.scalars().all() == [5, 5]


@pytest.mark.asyncio
async def test_fingerprint_is_matched_on_lookup(session):
    await cache_image_to_history(
        session, 1, None, "a cat", "uploads/cat.png", 7, fingerprint="fp-1"
    )

    assert await get_cached_image(session, 1, "a cat", 7, None, fingerprint="fp-1") == "uploads/cat.png"
    assert await get_cached_image(session, 1, "a cat", 7, None, fingerprint="fp-2") is None
