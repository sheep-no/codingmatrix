"""agent memory 上下文预算/摘要/知识去重修复回归测试（MEM4/MEM5/MEM6/MEM7）。"""
import re

from app.agent.memory import (
    AgentMemory,
    ConversationMemory,
    KnowledgeMemory,
    MemoryEntry,
)


class TestContextTokenBudget:
    """MEM4：get_with_context 应按 token 预算而非字符数截断。"""

    def test_ascii_entry_fits_token_budget(self):
        memory = ConversationMemory()
        memory.add(MemoryEntry(type="user", content="a" * 40))

        # 条目文本约 47 字符，字符口径会超过 20 预算；token 口径约 12 应纳入。
        context = memory.get_with_context(max_tokens=20)

        assert context != ""

    def test_cjk_entry_respects_token_budget(self):
        memory = ConversationMemory()
        memory.add(MemoryEntry(type="user", content="中文" * 30))

        # 60 个 CJK 字符约 60 token，超出 30 预算，不应纳入。
        assert memory.get_with_context(max_tokens=30) == ""


class TestSummaryCompression:
    """MEM5：压缩摘要不应把历史摘要再次摘要。"""

    def _summaries(self, memory: ConversationMemory):
        return [entry for entry in memory._entries if entry.type == "summary"]

    @staticmethod
    def _summarized_count(entry: MemoryEntry) -> int:
        match = re.search(r"共 (\d+) 条历史记录", entry.content)
        assert match is not None
        return int(match.group(1))

    def test_recompression_does_not_nest_previous_summary(self):
        memory = ConversationMemory(max_entries=100)
        memory._entries = [
            MemoryEntry(id="s0", type="summary", content="[对话摘要] 共 3 条历史记录，主要话题: 旧话题"),
            MemoryEntry(id="u0", type="user", content="AAA"),
            MemoryEntry(id="a0", type="assistant", content="BBB"),
        ] + [MemoryEntry(id=f"m{i}", type="user", content=f"消息 {i}") for i in range(14)]

        memory._compress_old_entries()

        summary = self._summaries(memory)[0]
        # 前 12 条参与压缩，其中 1 条是历史摘要，应只统计 11 条。
        assert self._summarized_count(summary) == 11
        # 历史摘要的话题不应混入新一轮摘要。
        assert "旧话题" not in summary.content


class TestSessionIdUniqueness:
    """MEM6：session_id 不应在同秒实例间冲突。"""

    def test_two_instances_do_not_collide(self):
        first = AgentMemory()
        second = AgentMemory()
        first._created_at = second._created_at = 1000.0

        assert first.session_id != second.session_id

    def test_session_id_has_sub_second_resolution(self):
        memory = AgentMemory()

        numeric_suffix = int(memory.session_id.split("_", 1)[1])

        assert numeric_suffix > 10**12


class TestKnowledgeImportancePreserved:
    """MEM7：同 key 覆盖不应降低 importance。"""

    def test_higher_importance_survives_overwrite(self):
        knowledge = KnowledgeMemory()
        knowledge.add(MemoryEntry(content="服务端口是 8000", metadata={"key": "port"}, importance=0.9))
        knowledge.add(MemoryEntry(content="服务端口是 8000", metadata={"key": "port"}, importance=0.5))

        existing = knowledge.get("port")
        assert existing is not None
        assert existing.importance == 0.9
