"""
多轮会话存储测试用例

测试内容：
1. Redis 存储基本操作
2. 数据库持久化
3. Redis + 数据库同步
4. 截断策略
5. 压缩策略
6. 故障恢复
"""
import pytest
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.conversation_store import ConversationStore, _estimate_tokens


class TestEstimateTokens:
    """Token 估算测试"""

    def test_empty_string(self):
        assert _estimate_tokens("") == 0

    def test_none(self):
        assert _estimate_tokens(None) == 0

    def test_english_text(self):
        # "hello world" = 11 chars / 2 = 5
        assert _estimate_tokens("hello world") == 5

    def test_chinese_text(self):
        # "你好世界" = 4 chars / 2 = 2
        assert _estimate_tokens("你好世界") == 2


class TestConversationStoreBasic:
    """基本存储操作测试"""

    @pytest.fixture
    def store(self):
        """创建测试用存储实例"""
        return ConversationStore("redis://localhost:6379/0")

    @pytest.fixture(autouse=True)
    def cleanup(self, store):
        """测试后清理"""
        yield
        # 清理测试数据
        try:
            store.redis.delete(store._key("test_session_1"))
            store.redis.delete(store._key("test_session_2"))
        except:
            pass

    def test_key_generation(self, store):
        """测试 Redis key 生成"""
        assert store._key("abc") == "conversation:abc"
        assert store._key("test_123") == "conversation:test_123"

    def test_save_and_get_redis(self, store):
        """测试 Redis 保存和读取"""
        messages = [
            {"role": "user", "content": "你好", "timestamp": int(time.time())},
            {"role": "assistant", "content": "你好！", "timestamp": int(time.time())},
        ]
        store._save_to_redis("test_session_1", messages)

        # 直接从 Redis 读取
        data = store.redis.get(store._key("test_session_1"))
        assert data is not None
        loaded = json.loads(data)
        assert len(loaded) == 2
        assert loaded[0]["role"] == "user"

    def test_redis_miss_returns_empty(self, store):
        """测试 Redis miss 返回空"""
        result = store.get_history("nonexistent_session")
        assert result == []


class TestConversationStoreSync:
    """Redis + 数据库同步测试"""

    @pytest.fixture
    def store(self):
        return ConversationStore("redis://localhost:6379/0")

    @pytest.fixture(autouse=True)
    def cleanup(self, store):
        yield
        try:
            store.redis.delete(store._key("test_sync_1"))
            store.redis.delete(store._key("test_sync_2"))
        except:
            pass

    @pytest.mark.asyncio
    async def test_append_writes_both(self, store):
        """测试 append_message 同时写入 Redis 和数据库"""
        await store.append_message("test_sync_1", "user_001", "user", "测试消息")

        # 验证 Redis 有数据
        redis_data = store.redis.get(store._key("test_sync_1"))
        assert redis_data is not None
        messages = json.loads(redis_data)
        assert len(messages) == 1
        assert messages[0]["content"] == "测试消息"

        # 验证数据库有数据
        db_data = await store._load_from_db_async("test_sync_1", "user_001")
        assert len(db_data) == 1
        assert db_data[0]["content"] == "测试消息"

    @pytest.mark.asyncio
    async def test_redis_miss_fallback_to_db(self, store):
        """测试 Redis miss 时从数据库加载"""
        # 先写入数据
        await store.append_message("test_sync_2", "user_001", "user", "消息1")
        await store.append_message("test_sync_2", "user_001", "assistant", "回复1")

        # 删除 Redis 缓存
        store.redis.delete(store._key("test_sync_2"))

        # 读取（应该从数据库回填）
        history = await store.get_history_async("test_sync_2", "user_001")
        assert len(history) >= 2  # 可能有多条（测试数据可能残留）
        contents = [m["content"] for m in history]
        assert "消息1" in contents
        assert "回复1" in contents

        # 验证 Redis 已回填
        redis_data = store.redis.get(store._key("test_sync_2"))
        assert redis_data is not None

    @pytest.mark.asyncio
    async def test_clear_clears_both(self, store):
        """测试 clear 同时清除 Redis 和数据库"""
        await store.append_message("test_sync_1", "user_001", "user", "测试")
        await store.clear_history("test_sync_1", "user_001")

        # Redis 应该清空
        redis_data = store.redis.get(store._key("test_sync_1"))
        assert redis_data is None

        # 数据库应该清空
        db_data = await store._load_from_db_async("test_sync_1", "user_001")
        assert len(db_data) == 0


class TestTruncationStrategy:
    """截断策略测试"""

    @pytest.fixture
    def store(self):
        return ConversationStore("redis://localhost:6379/0")

    def test_empty_messages(self, store):
        """测试空消息列表"""
        result = store.truncate_history([])
        assert result == []

    def test_within_limits(self, store):
        """测试未超限的情况"""
        messages = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
        ]
        result = store.truncate_history(messages, max_rounds=5)
        assert len(result) == 2

    def test_truncate_by_rounds(self, store):
        """测试按轮次截断"""
        # 10 轮 = 20 条消息
        messages = [
            {"role": "user", "content": f"msg{i}"} if i % 2 == 0
            else {"role": "assistant", "content": f"reply{i}"}
            for i in range(20)
        ]

        # 保留最近 3 轮 = 6 条消息
        result = store.truncate_history(messages, max_rounds=3)
        assert len(result) == 6
        # 应该保留最后 6 条
        assert result[0]["content"] == "msg14"

    def test_truncate_by_tokens(self, store):
        """测试按 token 数截断"""
        # 创建长消息
        long_content = "x" * 1000  # 约 500 token
        messages = [
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": long_content},
            {"role": "user", "content": "short"},
            {"role": "assistant", "content": "short"},
        ]

        # 限制 400 token，应该丢弃前面的长消息
        # 从后往前计算：short(2) + short(2) + long(500) = 504 > 400
        # 所以从 index 2 开始保留，结果是 2 条
        result = store.truncate_history(messages, max_tokens=400)
        assert len(result) == 2
        assert result[0]["content"] == "short"
        assert result[1]["content"] == "short"


class TestCompressionStrategy:
    """压缩策略测试"""

    @pytest.fixture
    def store(self):
        return ConversationStore("redis://localhost:6379/0")

    @pytest.mark.asyncio
    async def test_no_compression_when_within_limit(self, store):
        """测试未超限时不压缩"""
        messages = [
            {"role": "user", "content": "short msg"},
            {"role": "assistant", "content": "short reply"},
        ]

        mock_llm = AsyncMock(return_value="摘要")
        result = await store.compress_history(
            "test_session", "user_001", messages, mock_llm, max_tokens=4000
        )

        # 不应该调用 LLM
        mock_llm.assert_not_called()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_compression_when_exceeded(self, store):
        """测试超限时压缩"""
        # 创建超长消息
        long_content = "x" * 2000  # 约 1000 token
        messages = [
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": long_content},
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": long_content},
            {"role": "user", "content": "recent msg"},
            {"role": "assistant", "content": "recent reply"},
        ]

        mock_llm = AsyncMock(return_value="这是摘要")
        result = await store.compress_history(
            "test_comp", "user_001", messages, mock_llm, max_tokens=2000
        )

        # 应该调用 LLM
        mock_llm.assert_called_once()
        # 结果应该包含摘要 + 最近消息
        assert result[0]["role"] == "system"
        assert "摘要" in result[0]["content"]
        assert result[-1]["content"] == "recent reply"


class TestEdgeCases:
    """边界情况测试"""

    @pytest.fixture
    def store(self):
        return ConversationStore("redis://localhost:6379/0")

    @pytest.mark.asyncio
    async def test_concurrent_appends(self, store):
        """测试并发追加消息"""
        session_id = "test_concurrent"

        # 并发追加 10 条消息
        tasks = [
            store.append_message(session_id, "user_001", "user", f"msg{i}")
            for i in range(10)
        ]
        await asyncio.gather(*tasks)

        # 读取验证
        history = await store.get_history_async(session_id, "user_001")
        assert len(history) == 10

        # 清理
        await store.clear_history(session_id, "user_001")

    @pytest.mark.asyncio
    async def test_special_characters_in_content(self, store):
        """测试特殊字符内容"""
        special_content = '包含 "引号" 和 \n 换行 以及 emoji 🎉'
        await store.append_message("test_special", "user_001", "user", special_content)

        history = await store.get_history_async("test_special", "user_001")
        assert history[0]["content"] == special_content

        await store.clear_history("test_special", "user_001")

    @pytest.mark.asyncio
    async def test_very_long_content(self, store):
        """测试超长内容"""
        long_content = "x" * 100000  # 100KB
        await store.append_message("test_long", "user_001", "user", long_content)

        history = await store.get_history_async("test_long", "user_001")
        assert len(history[0]["content"]) == 100000

        await store.clear_history("test_long", "user_001")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
