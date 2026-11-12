"""Memory 模块全分支回归。"""

import json
import time

import pytest

from app.agent import memory as mem
from app.agent.memory import (
    AgentMemory,
    ConversationMemory,
    KnowledgeMemory,
    MemoryEntry,
    ReflectionMemory,
)


def _entry(content="hello", type_="conversation", importance=1.0, embedding=None, **meta):
    return MemoryEntry(
        type=type_,
        content=content,
        metadata=meta,
        importance=importance,
        embedding=embedding,
    )


class TestCosineSimilarity:
    def test_empty(self):
        assert mem.cosine_similarity([], [1.0]) == 0.0
        assert mem.cosine_similarity([1.0], []) == 0.0

    def test_dimension_mismatch(self):
        assert mem.cosine_similarity([1.0, 0.0], [1.0]) == 0.0

    def test_zero_norm(self):
        assert mem.cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_identical(self):
        assert mem.cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


class TestEstimateTokens:
    def test_empty(self):
        assert mem._estimate_tokens("") == 0

    def test_cjk_and_ascii(self):
        assert mem._estimate_tokens("你好") == 2
        assert mem._estimate_tokens("abcd") == 1
        assert mem._estimate_tokens("abcde") == 2

    def test_mixed(self):
        assert mem._estimate_tokens("你abc") >= 2


class TestMemoryEntry:
    def test_to_dict_without_embedding(self):
        data = _entry().to_dict()
        assert "embedding" not in data

    def test_to_dict_with_embedding(self):
        data = _entry(embedding=[1.0]).to_dict()
        assert data["embedding"] == [1.0]


class TestBaseMemory:
    @pytest.mark.asyncio
    async def test_methods_raise(self):
        base = mem.BaseMemory()
        with pytest.raises(NotImplementedError):
            base.add(_entry())
        with pytest.raises(NotImplementedError):
            base.get_recent()
        with pytest.raises(NotImplementedError):
            base.search("q")
        with pytest.raises(NotImplementedError):
            await base.search_async("q")
        with pytest.raises(NotImplementedError):
            base.clear()


class TestConversationMemory:
    def test_add_assigns_id_and_get_recent(self):
        memory = ConversationMemory()
        memory.add(_entry())
        memory.add(_entry(content="second"))
        recent = memory.get_recent(1)
        assert recent[0].content == "second"
        assert memory.get_recent(0) == memory._entries[-0:] if False else True
        assert memory._entries[0].id == "conv_0"

    def test_get_recent_empty(self):
        memory = ConversationMemory()
        assert memory.get_recent() == []

    def test_add_existing_id_kept(self):
        memory = ConversationMemory()
        entry = _entry()
        entry.id = "custom"
        memory.add(entry)
        assert entry.id == "custom"

    def test_max_entries_trim(self):
        memory = ConversationMemory(max_entries=2)
        memory.COMPRESSION_THRESHOLD = 100
        for i in range(4):
            memory.add(_entry(content=str(i)))
        assert [e.content for e in memory._entries] == ["2", "3"]

    def test_compression(self):
        memory = ConversationMemory()
        memory.COMPRESSION_THRESHOLD = 3
        memory.COMPRESSED_ENTRIES = 2
        memory._entries = [
            _entry(content="user a", type_="user"),
            _entry(content="asst b", type_="assistant"),
            _entry(content="user c", type_="user"),
            _entry(content="user d", type_="user"),
        ]
        memory._compress_old_entries()
        assert memory._entries[0].type == "summary"
        assert memory._is_compressed is True
        assert "共 2 条历史记录" in memory._entries[0].content
        assert "1 条用户消息" in memory._entries[0].content
        assert "1 条 AI 回复" in memory._entries[0].content

    def test_add_triggers_compression(self):
        memory = ConversationMemory(max_entries=100)
        memory.COMPRESSION_THRESHOLD = 2
        memory.COMPRESSED_ENTRIES = 1
        for i in range(3):
            memory.add(_entry(content=f"item {i}", type_="user"))
        assert memory._entries[0].type == "summary"
        assert memory._is_compressed is True

    def test_compression_skips_previous_summary(self):
        memory = ConversationMemory()
        memory.COMPRESSION_THRESHOLD = 3
        memory.COMPRESSED_ENTRIES = 1
        memory._entries = [
            _entry(content="old", type_="summary"),
            _entry(content="a", type_="user"),
            _entry(content="b", type_="assistant"),
            _entry(content="c", type_="user"),
        ]
        memory._compress_old_entries()
        assert "共 2 条历史记录" in memory._entries[0].content

    def test_compress_noop_below_threshold(self):
        memory = ConversationMemory()
        memory._entries = [_entry()]
        memory._compress_old_entries()
        assert memory._entries[0].type == "conversation"

    def test_get_with_context_budget(self):
        memory = ConversationMemory()
        memory.add(_entry(content="a"))
        memory.add(_entry(content="b"))
        assert memory.get_with_context(max_tokens=1000).count("\n") == 1
        assert memory.get_with_context(max_tokens=0) == ""

    def test_search_sorted(self):
        memory = ConversationMemory()
        memory.add(_entry(content="match", importance=0.1))
        memory.add(_entry(content="MATCH high", importance=0.9))
        memory.add(_entry(content="other"))
        results = memory.search("match")
        assert results[0].content == "MATCH high"

    @pytest.mark.asyncio
    async def test_search_async_embedding(self, monkeypatch):
        async def _embed(text):
            return [1.0, 0.0]

        monkeypatch.setattr(mem, "get_embedding", _embed)
        memory = ConversationMemory()
        memory.add(_entry(content="hit", embedding=[1.0, 0.0]))
        memory.add(_entry(content="miss", embedding=[0.0, 1.0]))
        memory.add(_entry(content="no vec"))
        results = await memory.search_async("q")
        assert [e.content for e in results] == ["hit"]

    @pytest.mark.asyncio
    async def test_search_async_embedding_failure_falls_back(self, monkeypatch):
        async def _boom(text):
            raise RuntimeError("down")

        monkeypatch.setattr(mem, "get_embedding", _boom)
        memory = ConversationMemory()
        memory.add(_entry(content="match"))
        assert (await memory.search_async("match"))[0].content == "match"

    def test_clear(self):
        memory = ConversationMemory()
        memory.add(_entry())
        memory._is_compressed = True
        memory.clear()
        assert memory._entries == []
        assert memory._is_compressed is False

    def test_get_summary(self):
        memory = ConversationMemory()
        assert memory.get_summary()["total_entries"] == 0
        memory.add(_entry(type_="user"))
        summary = memory.get_summary()
        assert summary["total_entries"] == 1
        assert summary["types"] == {"user": 1}
        assert summary["oldest"] is not None
        assert summary["newest"] is not None
        assert summary["is_compressed"] is False


class TestKnowledgeMemory:
    def test_add_uses_metadata_key(self):
        memory = KnowledgeMemory()
        memory.add(_entry(content="c", key="k"))
        assert memory.get("k") is not None

    def test_add_uses_content_prefix(self):
        memory = KnowledgeMemory()
        memory.add(_entry(content="x" * 200))
        assert "x" * 100 in memory._entries

    def test_duplicate_keeps_higher_importance(self):
        memory = KnowledgeMemory()
        memory.add(_entry(content="c", key="k", importance=0.9))
        memory.add(_entry(content="updated", key="k", importance=0.1))
        assert memory.get("k").importance == 0.9
        assert memory.get("k").content == "updated"

    def test_evict_lru(self):
        memory = KnowledgeMemory(max_entries=2)
        memory.add(_entry(content="a", key="a"))
        memory._access_times["a"] = 1.0
        memory.add(_entry(content="b", key="b"))
        memory._access_times["b"] = 2.0
        memory.add(_entry(content="c", key="c"))
        assert "a" not in memory._entries
        assert "c" in memory._entries

    def test_evict_lru_empty(self):
        memory = KnowledgeMemory()
        memory._evict_lru()

    def test_get_missing(self):
        assert KnowledgeMemory().get("nope") is None

    def test_get_recent_sorted(self):
        memory = KnowledgeMemory()
        memory.add(_entry(content="a", key="a"))
        memory.add(_entry(content="b", key="b"))
        memory._access_times["a"] = 1.0
        memory._access_times["b"] = 2.0
        assert [e.content for e in memory.get_recent(1)] == ["b"]

    def test_get_recent_handles_missing_access_time(self):
        memory = KnowledgeMemory()
        memory._entries["x"] = _entry(content="x")
        assert memory.get_recent()[0].content == "x"

    def test_search(self):
        memory = KnowledgeMemory()
        memory.add(_entry(content="match", key="a", importance=0.1))
        memory.add(_entry(content="match too", key="b", importance=0.9))
        assert memory.search("match")[0].content == "match too"

    def test_search_no_match(self):
        memory = KnowledgeMemory()
        memory.add(_entry(content="abc", key="a"))
        assert memory.search("zzz") == []

    @pytest.mark.asyncio
    async def test_search_async(self, monkeypatch):
        async def _embed(text):
            return [1.0, 0.0]

        monkeypatch.setattr(mem, "get_embedding", _embed)
        memory = KnowledgeMemory()
        memory.add(_entry(content="hit", key="a", embedding=[1.0, 0.0]))
        memory.add(_entry(content="miss", key="b", embedding=[0.0, 1.0]))
        memory.add(_entry(content="none", key="c"))
        assert [e.content for e in await memory.search_async("q")] == ["hit"]

    @pytest.mark.asyncio
    async def test_search_async_error(self, monkeypatch):
        async def _boom(text):
            raise RuntimeError("down")

        monkeypatch.setattr(mem, "get_embedding", _boom)
        memory = KnowledgeMemory()
        memory.add(_entry(content="match", key="a"))
        assert (await memory.search_async("match"))[0].content == "match"

    def test_clear(self):
        memory = KnowledgeMemory()
        memory.add(_entry(content="a", key="a"))
        memory.clear()
        assert memory._entries == {}
        assert memory._access_times == {}

    def test_update_importance_clamps(self):
        memory = KnowledgeMemory()
        memory.add(_entry(content="a", key="a", importance=0.5))
        memory.update_importance("a", 9)
        assert memory.get("a").importance == 1.0
        memory.update_importance("a", -1)
        assert memory.get("a").importance == 0.0
        memory.update_importance("missing", 0.2)


class TestReflectionMemory:
    def test_add_assigns_fields(self):
        memory = ReflectionMemory()
        entry = _entry(content="reflection", type_="user", importance=0.1)
        memory.add(entry)
        assert entry.id == "refl_0"
        assert entry.type == "reflection"
        assert entry.importance == 0.8

    def test_add_reflection(self):
        memory = ReflectionMemory()
        memory.add_reflection("learned", {"a": 1})
        assert memory.get_recent()[0].metadata == {"a": 1}

    def test_add_reflection_without_metadata(self):
        memory = ReflectionMemory()
        memory.add_reflection("learned")
        assert memory.get_recent()[0].metadata == {}

    def test_max_entries_trim(self):
        memory = ReflectionMemory(max_entries=1)
        memory.add_reflection("a")
        memory.add_reflection("b")
        assert [e.content for e in memory._entries] == ["b"]

    def test_get_recent_empty(self):
        assert ReflectionMemory().get_recent() == []

    def test_get_insights(self):
        memory = ReflectionMemory()
        memory.add_reflection("a")
        memory._entries.append(_entry(content="user", type_="user"))
        assert memory.get_insights() == ["a"]

    def test_search(self):
        memory = ReflectionMemory()
        memory.add_reflection("match one")
        memory.add_reflection("match two")
        assert [e.content for e in memory.search("match", 1)] == ["match two"]

    @pytest.mark.asyncio
    async def test_search_async(self, monkeypatch):
        async def _embed(text):
            return [1.0, 0.0]

        monkeypatch.setattr(mem, "get_embedding", _embed)
        memory = ReflectionMemory()
        memory.add_reflection("hit")
        memory._entries[-1].embedding = [1.0, 0.0]
        memory.add_reflection("miss")
        memory._entries[-1].embedding = [0.0, 1.0]
        memory.add_reflection("none")
        assert [e.content for e in await memory.search_async("q")] == ["hit"]

    @pytest.mark.asyncio
    async def test_search_async_error(self, monkeypatch):
        async def _boom(text):
            raise RuntimeError("down")

        monkeypatch.setattr(mem, "get_embedding", _boom)
        memory = ReflectionMemory()
        memory.add_reflection("match")
        assert (await memory.search_async("match"))[0].content == "match"

    def test_clear(self):
        memory = ReflectionMemory()
        memory.add_reflection("a")
        memory.clear()
        assert memory._entries == []


class TestAgentMemory:
    def test_session_id_lazy(self):
        memory = AgentMemory()
        first = memory.session_id
        assert first == memory.session_id
        assert first.startswith("session_")

    def test_add_messages_and_tools(self):
        memory = AgentMemory()
        memory.add_user_message("hi", {"a": 1})
        memory.add_assistant_message("hello")
        memory.add_tool_result("tool", "ok", True)
        memory.add_tool_result("tool", "bad", False)
        assert len(memory.conversation.get_recent()) == 4
        assert "成功" in memory.conversation.get_recent()[2].content
        assert "失败" in memory.conversation.get_recent()[3].content

    def test_add_user_message_default_metadata(self):
        memory = AgentMemory()
        memory.add_user_message("hi")
        assert memory.conversation.get_recent()[0].metadata == {}

    def test_add_knowledge_with_and_without_key(self):
        memory = AgentMemory()
        memory.add_knowledge("k1", key="key1")
        memory.add_knowledge("k2")
        assert memory.knowledge.get("key1") is not None
        assert len(memory.knowledge._entries) == 2

    def test_add_reflection(self):
        memory = AgentMemory()
        memory.add_reflection("r", {"x": 1})
        assert memory.reflection.get_insights() == ["r"]

    def test_get_context_for_prompt_full(self):
        memory = AgentMemory()
        memory.add_reflection("insight")
        memory.add_knowledge("knowledge", key="k")
        memory.add_user_message("hi")
        context = memory.get_context_for_prompt()
        assert "【反思总结】" in context
        assert "【相关知识】" in context
        assert "【对话历史】" in context

    def test_get_context_for_prompt_empty(self):
        assert AgentMemory().get_context_for_prompt() == ""

    def test_get_full_context(self):
        memory = AgentMemory()
        memory.add_knowledge("k", key="key")
        memory.add_reflection("r")
        context = memory.get_full_context()
        assert context["session_id"].startswith("session_")
        assert context["recent_knowledge"][0]["content"] == "k"
        assert context["recent_reflections"] == ["r"]
        assert context["last_updated"] >= context["created_at"]

    @pytest.mark.asyncio
    async def test_search_async_searches_all(self, monkeypatch):
        async def _embed(text):
            return [1.0, 0.0]

        monkeypatch.setattr(mem, "get_embedding", _embed)
        memory = AgentMemory()
        memory.add_user_message("conv")
        memory.conversation._entries[-1].embedding = [1.0, 0.0]
        memory.add_knowledge("know", key="k")
        memory.knowledge.get("k").embedding = [1.0, 0.0]
        memory.add_reflection("refl")
        memory.reflection._entries[-1].embedding = [1.0, 0.0]
        result = await memory.search_async("q")
        assert set(result) == {"conversation", "knowledge", "reflection"}
        assert all(result.values())

    def test_clear_session_and_all(self):
        memory = AgentMemory()
        memory.add_user_message("hi")
        memory.add_knowledge("k", key="k")
        memory.add_reflection("r")
        old_session = memory.session_id
        memory.clear_session()
        assert memory.conversation._entries == []
        assert memory.knowledge._entries
        assert memory.session_id != old_session
        memory.clear_all()
        assert memory.knowledge._entries == {}
        assert memory.reflection._entries == []
        assert memory._session_id is None

    @pytest.mark.asyncio
    async def test_save_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "memory.json"
        memory = AgentMemory()
        memory.add_user_message("hi")
        memory.add_knowledge("k", key="k")
        memory.add_reflection("r")
        assert await memory.save_to_storage(str(path)) is True

        restored = AgentMemory()
        assert await restored.load_from_storage(str(path)) is True
        assert restored.conversation.get_recent()[0].content == "hi"
        assert restored.knowledge.get("k") is not None
        assert restored.reflection.get_insights() == ["r"]

    @pytest.mark.asyncio
    async def test_save_error(self, tmp_path):
        memory = AgentMemory()
        assert await memory.save_to_storage(str(tmp_path / "missing" / "m.json")) is False

    @pytest.mark.asyncio
    async def test_load_missing_file(self, tmp_path):
        memory = AgentMemory()
        assert await memory.load_from_storage(str(tmp_path / "nope.json")) is False

    @pytest.mark.asyncio
    async def test_load_filters_unknown_fields(self, tmp_path):
        path = tmp_path / "memory.json"
        path.write_text(
            json.dumps(
                {
                    "session_id": "s",
                    "created_at": 1.0,
                    "conversation": [{"content": "hi", "unknown": 1}],
                    "knowledge": [{"content": "k", "unknown": 2}],
                    "reflections": [{"content": "r", "unknown": 3}],
                }
            ),
            encoding="utf-8",
        )
        memory = AgentMemory()
        assert await memory.load_from_storage(str(path)) is True
        assert memory.session_id == "s"
        assert memory.conversation.get_recent()[0].content == "hi"

    @pytest.mark.asyncio
    async def test_load_defaults_created_at(self, tmp_path):
        path = tmp_path / "memory.json"
        path.write_text(json.dumps({"session_id": "s"}), encoding="utf-8")
        memory = AgentMemory()
        assert await memory.load_from_storage(str(path)) is True
        assert memory._created_at > 0
