"""历史搜索列表与计数口径一致性回归（db_layer.md DB7）。

原实现：列表把关键词套在「每会话最新一条」结果集上，计数把关键词放
子查询内（任一条命中）——同一关键词两种语义，导致早期消息命中的会话
从列表漏召回，而计数仍计入，翻页出现空页。
"""

import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.search_history import (
    get_distinct_conversation_count,
    search_history_to_db,
)
from app.models.history import History
from app.models.user import User


def _history(user_id: str, conversation_id: int, prompt: str) -> History:
    return History(
        user_id=user_id,
        conversation_id=conversation_id,
        prompt=prompt,
        response="r",
    )


@pytest.fixture()
async def search_user(test_db: AsyncSession):
    """自建独立用户，避免复用共享的 test_user 影响其它用例的 id 分配。"""
    user = User(
        id=990001,
        username="search-semantics-user",
        email="search-semantics@example.com",
        hashed_password="x",
    )
    test_db.add(user)
    await test_db.commit()
    yield user
    await test_db.execute(delete(History).where(History.user_id == str(user.id)))
    await test_db.execute(delete(User).where(User.id == user.id))
    await test_db.commit()


@pytest.mark.asyncio
async def test_earlier_message_match_is_recalled_and_counted_once(
    test_db: AsyncSession,
    search_user,
):
    keyword = f"needle-{uuid.uuid4().hex[:8]}"
    user_id = str(search_user.id)

    # 会话 900001：早期消息命中关键词，最新一条不含
    test_db.add(_history(user_id, 900001, f"{keyword} 早期消息"))
    test_db.add(_history(user_id, 900001, "最新一条不含关键词"))
    # 会话 900002：完全不含关键词
    test_db.add(_history(user_id, 900002, "无关内容"))
    await test_db.commit()

    histories = await search_history_to_db(
        db=test_db, user_id=user_id, prompt_keyword=keyword, limit=20, offset=0
    )
    total = await get_distinct_conversation_count(
        db=test_db, user_id=user_id, prompt_keyword=keyword
    )

    # 列表召回命中会话，且展示该会话的最新一条
    assert [h.conversation_id for h in histories] == [900001]
    assert histories[0].prompt == "最新一条不含关键词"
    # 计数与列表口径一致
    assert total == len(histories) == 1


@pytest.mark.asyncio
async def test_non_matching_conversation_is_excluded_from_both(
    test_db: AsyncSession,
    search_user,
):
    keyword = f"absent-{uuid.uuid4().hex[:8]}"
    user_id = str(search_user.id)

    test_db.add(_history(user_id, 900003, "没有任何关键词"))
    await test_db.commit()

    assert await search_history_to_db(
        db=test_db, user_id=user_id, prompt_keyword=keyword
    ) == []
    assert await get_distinct_conversation_count(
        db=test_db, user_id=user_id, prompt_keyword=keyword
    ) == 0
