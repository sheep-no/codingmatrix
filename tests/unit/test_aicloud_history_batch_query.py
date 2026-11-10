"""aicloud 历史列表应批量取消息，避免按会话逐个查询。

`GET /aicloud/history` 最多返回 100 个会话。旧实现对每个会话各发一条
`select(AicloudMessage)`，单次请求最多 1+100 次数据库往返。修复后先用
`session_id IN (...)` 一次取回，再按会话分组。
"""

import pytest

import app.api.v1.aicloud as aicloud_api
from app.models.aicloud import AicloudMessage, AicloudSession


async def _allow(user_id, db):
    return None


def _message_selects(statements):
    """Only count the SELECTs that target AicloudMessage."""
    selected = []
    for stmt in statements:
        text = str(stmt)
        if "aicloud_messages" in text and "SELECT" in text.upper():
            selected.append(text)
    return selected


class _RecordingSession:
    """Proxy an AsyncSession while recording every execute() statement."""

    def __init__(self, inner):
        self._inner = inner
        self.statements = []

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        return await self._inner.execute(statement, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


@pytest.mark.asyncio
async def test_history_batches_message_query(test_db, monkeypatch):
    monkeypatch.setattr(aicloud_api, "check_aicloud_permission", _allow)

    user_id = 6101
    for index in range(6):
        session_id = f"session-{index}"
        test_db.add(AicloudSession(id=session_id, user_id=user_id))
        test_db.add(
            AicloudMessage(session_id=session_id, role="user", content=f"msg-{index}")
        )
    await test_db.commit()

    db = _RecordingSession(test_db)
    sessions = await aicloud_api.get_history(
        days=10, limit=50, offset=0, db=db, user_id=user_id
    )

    assert len(sessions) == 6
    by_session = {item.id: item.messages[0].content for item in sessions}
    assert by_session == {f"session-{i}": f"msg-{i}" for i in range(6)}
    # 1 个会话查询 + 1 个消息批量查询；旧实现是 1 + 6。
    assert len(_message_selects(db.statements)) == 1


@pytest.mark.asyncio
async def test_history_returns_empty_without_sessions(test_db, monkeypatch):
    monkeypatch.setattr(aicloud_api, "check_aicloud_permission", _allow)

    user_id = 6102
    db = _RecordingSession(test_db)
    sessions = await aicloud_api.get_history(
        days=10, limit=50, offset=0, db=db, user_id=user_id
    )

    assert sessions == []
    assert _message_selects(db.statements) == []
