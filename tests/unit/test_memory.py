"""
Agent Memory 模块单元测试
测试 ConversationMemory, KnowledgeMemory 和 AgentMemory 系统
"""
import pytest
import time
from app.agent.memory import MemoryEntry, ConversationMemory, KnowledgeMemory


@pytest.fixture
def memory_entry():
    """创建示例记忆条目"""
    return MemoryEntry(
        id="test_1",
        type="user",
        content="Hello, world!",
        metadata={"session_id": "session_1"},
        importance=0.8,
    )


@pytest.fixture
def conv_memory():
    """创建对话记忆实例"""
    return ConversationMemory(max_entries=50)


class TestMemoryEntry:
    """MemoryEntry 数据类测试"""

    def test_create_entry(self):
        """测试创建记忆条目"""
        entry = MemoryEntry(
            type="assistant",
            content="Response text",
            importance=0.9,
        )
        assert entry.type == "assistant"
        assert entry.content == "Response text"
        assert entry.importance == 0.9
        assert entry.id is None
        assert entry.embedding is None

    def test_entry_default_values(self):
        """测试默认值"""
        entry = MemoryEntry()
        assert entry.type == "conversation"
        assert entry.content == ""
        assert entry.metadata == {}
        assert entry.importance == 1.0

    def test_entry_to_dict(self, memory_entry):
        """测试转换为字典"""
        d = memory_entry.to_dict()
        assert d["id"] == "test_1"
        assert d["type"] == "user"
        assert d["content"] == "Hello, world!"
        assert d["metadata"] == {"session_id": "session_1"}
        assert d["importance"] == 0.8
