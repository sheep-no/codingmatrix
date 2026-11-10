"""AICloud 聊天端点必须校验会话归属。

`session_id` 由客户端提供。原实现按 id 查询会话时没有限定 `user_id`，
命中他人会话后直接读取历史消息并追加新消息，可越权读取/污染他人会话。
"""

import pytest
from fastapi import HTTPException

import app.api.v1.aicloud as aicloud_api
from app.models.aicloud import AicloudMessage, AicloudSession
from app.schema.aicloud import ChatRequest, ChatStreamRequest


async def _allow(user_id, db):
    return None


@pytest.mark.asyncio
async def test_chat_rejects_session_owned_by_other_user(test_db, monkeypatch):
    monkeypatch.setattr(aicloud_api, "check_aicloud_permission", _allow)

    test_db.add(AicloudSession(id="victim-session", user_id=999))
    test_db.add(
        AicloudMessage(session_id="victim-session", role="user", content="secret")
    )
    await test_db.commit()

    with pytest.raises(HTTPException) as excinfo:
        await aicloud_api.chat(
            request=ChatRequest(message="hi", session_id="victim-session"),
            db=test_db,
            user_id=1,
        )

    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_chat_stream_rejects_session_owned_by_other_user(test_db, monkeypatch):
    monkeypatch.setattr(aicloud_api, "check_aicloud_permission", _allow)

    test_db.add(AicloudSession(id="victim-stream", user_id=999))
    await test_db.commit()

    with pytest.raises(HTTPException) as excinfo:
        await aicloud_api.chat_stream(
            request=ChatStreamRequest(message="hi", session_id="victim-stream"),
            db=test_db,
            user_id=1,
        )

    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_chat_creates_own_session_normally(test_db, monkeypatch):
    monkeypatch.setattr(aicloud_api, "check_aicloud_permission", _allow)

    # 走到创建会话后即返回，避免触发真实 LLM 调用。
    async def _stop(*args, **kwargs):
        raise RuntimeError("stop-after-session")

    monkeypatch.setattr(aicloud_api, "ensure_session", _stop)

    with pytest.raises(RuntimeError, match="stop-after-session"):
        await aicloud_api.chat(
            request=ChatRequest(message="hi", session_id="fresh-session"),
            db=test_db,
            user_id=1,
        )

    created = await test_db.get(AicloudSession, "fresh-session")
    assert created is not None
    assert created.user_id == 1
