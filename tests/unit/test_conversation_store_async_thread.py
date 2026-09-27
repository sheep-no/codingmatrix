"""回归测试：ConversationStore 的 async 方法不得同步阻塞事件循环。

`get_history_async` / `append_message` / `clear_history` 内部使用同步
`redis` 客户端；直接调用会占住事件循环，必须投递到线程池执行。
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import app.agent.conversation_store as cs
from app.agent.conversation_store import ConversationStore


def _make_store(monkeypatch):
    store = ConversationStore.__new__(ConversationStore)
    store.redis = MagicMock()
    store.redis.get.return_value = None
    store.redis.exists.return_value = True
    store.redis.delete.return_value = 1
    store._append_lock = asyncio.Lock()

    calls = []

    async def fake_to_thread(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(cs.asyncio, "to_thread", fake_to_thread)
    return store, calls


async def test_get_history_async_offloads_redis_get(monkeypatch):
    store, calls = _make_store(monkeypatch)
    monkeypatch.setattr(store, "_load_from_db_async", AsyncMock(return_value=[]))

    await store.get_history_async("s1", "u1")

    assert calls == [store.redis.get]


async def test_get_history_async_offloads_redis_writeback(monkeypatch):
    store, calls = _make_store(monkeypatch)
    monkeypatch.setattr(
        store,
        "_load_from_db_async",
        AsyncMock(return_value=[{"role": "user", "content": "hi"}]),
    )

    await store.get_history_async("s1", "u1")

    assert calls == [store.redis.get, store._save_to_redis]
    store.redis.setex.assert_called_once()


async def test_append_message_offloads_exists_and_append(monkeypatch):
    store, calls = _make_store(monkeypatch)
    monkeypatch.setattr(store, "_save_message_to_db", AsyncMock(return_value=True))

    ok = await store.append_message("s1", "u1", "user", "hi")

    assert ok is True
    assert calls == [store.redis.exists, store._append_to_redis]


async def test_clear_history_offloads_redis_delete(monkeypatch):
    store, calls = _make_store(monkeypatch)

    await store.clear_history("s1")

    assert calls == [store.redis.delete]
