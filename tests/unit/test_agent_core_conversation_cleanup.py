"""ConversationHistoryManager 会话清理顺序测试。

历史消息 dict 只含 role/content/tool_call_id，没有 timestamp 字段，
清理逻辑曾按 messages[-1].get("timestamp", 0) 排序，导致所有会话 key
恒为 0，实际退化为按插入顺序移除，把最新会话清掉、留下最旧会话。
"""
import pytest

from app.utils.agent_core import ConversationHistoryManager


@pytest.mark.asyncio
async def test_cleanup_evicts_oldest_sessions():
    mgr = ConversationHistoryManager()
    mgr.MAX_ACTIVE_SESSIONS = 3

    for i in range(1, 6):
        await mgr.add_messages(f"s{i}", [{"role": "user", "content": f"msg{i}"}])

    remaining = set(mgr._data.keys())
    assert remaining == {"s3", "s4", "s5"}


@pytest.mark.asyncio
async def test_recently_updated_session_is_kept():
    mgr = ConversationHistoryManager()
    mgr.MAX_ACTIVE_SESSIONS = 2

    await mgr.add_messages("a", [{"role": "user", "content": "1"}])
    await mgr.add_messages("b", [{"role": "user", "content": "1"}])
    # 重新激活 a，应保留 a 与最新加入的 c，淘汰 b
    await mgr.add_messages("a", [{"role": "assistant", "content": "2"}])
    await mgr.add_messages("c", [{"role": "user", "content": "1"}])

    assert set(mgr._data.keys()) == {"a", "c"}
