"""对话归档窗口与分页回归（db_layer.md DB4）。

原实现两个缺陷：
1. 窗口固定 [now-13d, now-3d)，调度错过一整轮后中间时间带永久逃逸归档；
2. 用户分页用 offset，而归档会物理删除消息，消息被清空的用户从
   distinct 集合消失使 offset 漂移，后续用户被整批跳过。
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import chat_archiver as archiver_module
from app.db.chat_archiver import ChatArchiver
from app.models.chat_history import ChatHistory, ChatSummary
from app.models.user import User


class _SameSession:
    """让 ChatArchiver 内部 `async_session()` 复用测试会话。"""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture()
async def archive_user_factory(test_db: AsyncSession):
    created: list[int] = []

    async def _make(user_id: int):
        test_db.add(
            User(
                id=user_id,
                username=f"archiver-{user_id}",
                email=f"archiver-{user_id}@example.com",
                hashed_password="x",
            )
        )
        created.append(user_id)
        await test_db.commit()
        return user_id

    yield _make

    for user_id in created:
        for model in (ChatHistory, ChatSummary):
            await test_db.execute(model.__table__.delete().where(model.user_id == user_id))
        await test_db.execute(User.__table__.delete().where(User.id == user_id))
    await test_db.commit()


@pytest.fixture()
def stub_summary(monkeypatch):
    """替换外部依赖，只保留窗口/分页逻辑在真实 DB 上执行。"""
    monkeypatch.setattr(
        ChatArchiver,
        "_generate_summary_with_ai",
        lambda self, messages: _return("摘要"),
    )

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(archiver_module, "save_summary_checkpoint", _noop)
    monkeypatch.setattr(archiver_module, "delete_messages_for_legacy_ids", _noop)


def _return(value):
    async def _coro(*args, **kwargs):
        return value

    return _coro()


@pytest.mark.asyncio
async def test_missed_band_is_archived_via_watermark(
    test_db: AsyncSession,
    archive_user_factory,
    stub_summary,
):
    user_id = await archive_user_factory(810001)
    now = datetime.utcnow()

    # 上一轮归档止于 20 天前
    test_db.add(
        ChatSummary(
            user_id=user_id,
            summary_text="旧摘要",
            start_date=now - timedelta(days=30),
            end_date=now - timedelta(days=20),
        )
    )
    # 落在「错过一轮」带里的消息：早于 13 天，固定窗口会漏掉
    test_db.add(
        ChatHistory(
            user_id=user_id,
            role="user",
            content="错过的消息",
            is_archived=False,
            created_at=now - timedelta(days=17),
        )
    )
    await test_db.commit()

    await ChatArchiver(test_db)._archive_user(user_id, days_ago_start=3, days_ago_end=13)

    remaining = (
        await test_db.execute(
            select(func.count()).select_from(ChatHistory).where(ChatHistory.user_id == user_id)
        )
    ).scalar()
    summaries = (
        await test_db.execute(
            select(func.count()).select_from(ChatSummary).where(ChatSummary.user_id == user_id)
        )
    ).scalar()
    assert remaining == 0, "错过时间带的消息应被归档并硬删除"
    assert summaries == 2, "应在旧摘要之外补一条覆盖该时间带的摘要"


@pytest.mark.asyncio
async def test_offset_free_pagination_does_not_skip_users(
    test_db: AsyncSession,
    archive_user_factory,
    stub_summary,
    monkeypatch,
):
    first = await archive_user_factory(810002)
    second = await archive_user_factory(810003)
    now = datetime.utcnow()

    for user_id in (first, second):
        test_db.add(
            ChatHistory(
                user_id=user_id,
                role="user",
                content="旧消息",
                is_archived=False,
                created_at=now - timedelta(days=5),
            )
        )
    await test_db.commit()

    monkeypatch.setattr(archiver_module, "async_session", lambda: _SameSession(test_db))

    await ChatArchiver(test_db).archive_all_users(
        days_ago_start=3, days_ago_end=13, batch_size=1
    )

    for user_id in (first, second):
        remaining = (
            await test_db.execute(
                select(func.count()).select_from(ChatHistory).where(ChatHistory.user_id == user_id)
            )
        ).scalar()
        summaries = (
            await test_db.execute(
                select(func.count())
                .select_from(ChatSummary)
                .where(ChatSummary.user_id == user_id)
            )
        ).scalar()
        assert remaining == 0, f"用户 {user_id} 的消息应被归档"
        assert summaries == 1, f"用户 {user_id} 不应因分页漂移被跳过"
