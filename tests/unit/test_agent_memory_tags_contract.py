"""知识条目 tags 契约回归。

KnowledgeRequest/KnowledgeResponse 和前端一直传递 tags，但服务层 add_knowledge
曾缺少该形参，调用方会收到 TypeError 而写入失败。
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent_memory import KnowledgeEntry
from app.services.agent_memory_service import AgentMemoryService


@pytest.mark.asyncio
async def test_add_knowledge_accepts_and_persists_tags():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(KnowledgeEntry.__table__.create)
    session = async_sessionmaker(engine, expire_on_commit=False)()
    try:
        service = AgentMemoryService(session)

        tagged = await service.add_knowledge(
            user_id=1, content="部署前先跑迁移", tags=["migration", "ops"]
        )
        untagged = await service.add_knowledge(user_id=1, content="普通知识")

        assert tagged.tags == ["migration", "ops"]
        assert untagged.tags == []
    finally:
        await session.close()
        await engine.dispose()
