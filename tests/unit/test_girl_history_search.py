"""GirlAi 历史搜索必须转义 LIKE 通配符，且 total 反映匹配总数（GIR4）。

原实现直接把 q 拼进 ilike，用户输入 `%` 会匹配全部记录；total 用当前页
记录数，分页语义失真。
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1.GirlAi import _escape_like, search_history
from app.models.chat_history import ChatHistory


def test_escape_like_escapes_wildcards():
    assert _escape_like("50%_x") == "50\\%\\_x"
    assert _escape_like("a\\b") == "a\\\\b"
    assert _escape_like("plain") == "plain"


@pytest.mark.asyncio
async def test_search_escapes_wildcards_and_reports_total():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(ChatHistory.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = 987654
    try:
        async with session_factory() as session:
            session.add_all(
                [
                    ChatHistory(user_id=user_id, role="user", content="50% off", is_archived=False),
                    ChatHistory(user_id=user_id, role="user", content="plain text", is_archived=False),
                    ChatHistory(user_id=user_id, role="user", content="another", is_archived=False),
                    ChatHistory(user_id=user_id, role="user", content="archived 50%", is_archived=True),
                ]
            )
            await session.commit()

            result = await search_history(
                q="%", token={"sub": str(user_id)}, db=session, limit=20, offset=0
            )

            # "%" 被转义为字面量：只命中未归档且含 "%" 的一条
            assert result["total"] == 1
            assert [record["content"] for record in result["records"]] == ["50% off"]
    finally:
        await engine.dispose()
