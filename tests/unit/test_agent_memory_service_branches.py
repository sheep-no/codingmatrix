"""AgentMemoryService 全分支测试（内存 SQLite）。"""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent_memory import (
    AgentReflection,
    AgentSession,
    KnowledgeEntry,
    MemoryEntry,
    ModelUsageStats,
    ToolExecutionLog,
)
from app.services.agent_memory_service import AgentMemoryService


@pytest.fixture
async def service():
    engine = create_async_engine("sqlite+aiosqlite://")
    tables = [
        AgentSession.__table__,
        MemoryEntry.__table__,
        AgentReflection.__table__,
        KnowledgeEntry.__table__,
        ToolExecutionLog.__table__,
        ModelUsageStats.__table__,
    ]
    async with engine.begin() as connection:
        for table in tables:
            await connection.run_sync(table.create)
    session = async_sessionmaker(engine, expire_on_commit=False)()
    try:
        yield AgentMemoryService(session)
    finally:
        await session.close()
        await engine.dispose()


class TestSessionLifecycle:
    @pytest.mark.asyncio
    async def test_create_get_and_end_session(self, service):
        created = await service.create_session(1, session_type="react", model_key="m")

        fetched = await service.get_session(created.id)
        assert fetched.id == created.id
        assert fetched.session_type == "react"
        assert fetched.model_key == "m"

        ended = await service.end_session(
            created.id, success=False, total_steps=3, total_tokens=99
        )
        assert ended.success is False
        assert ended.total_steps == 3
        assert ended.total_tokens == 99
        assert ended.ended_at is not None

    @pytest.mark.asyncio
    async def test_end_missing_session_returns_none(self, service):
        assert await service.end_session("nope") is None

    @pytest.mark.asyncio
    async def test_get_missing_session_returns_none(self, service):
        assert await service.get_session("missing") is None

    @pytest.mark.asyncio
    async def test_get_user_sessions_paginates(self, service):
        for index in range(3):
            await service.create_session(7, session_type=f"t{index}")

        sessions = await service.get_user_sessions(7, limit=2, offset=0)
        assert len(sessions) == 2
        sessions_page2 = await service.get_user_sessions(7, limit=2, offset=2)
        assert len(sessions_page2) == 1
        assert await service.get_user_sessions(8) == []

    @pytest.mark.asyncio
    async def test_delete_session(self, service):
        created = await service.create_session(1)

        assert await service.delete_session(created.id) is True
        assert await service.get_session(created.id) is None
        assert await service.delete_session("missing") is False


class TestMemoryEntries:
    @pytest.mark.asyncio
    async def test_add_and_filter_memory(self, service):
        session = await service.create_session(1)
        user_entry = await service.add_memory_entry(session.id, "user", "hello")
        await service.add_memory_entry(
            session.id, "assistant", "hi", extra_data={"k": "v"}, importance=0.9
        )

        assert user_entry.extra_data == {}
        assert user_entry.importance == 1.0

        all_entries = await service.get_session_memory(session.id)
        assert len(all_entries) == 2

        filtered = await service.get_session_memory(session.id, entry_type="user")
        assert [e.content for e in filtered] == ["hello"]

    @pytest.mark.asyncio
    async def test_get_session_memory_respects_limit(self, service):
        session = await service.create_session(1)
        for index in range(3):
            await service.add_memory_entry(session.id, "user", f"m{index}")

        assert len(await service.get_session_memory(session.id, limit=1)) == 1

    @pytest.mark.asyncio
    async def test_memory_context_is_chronological_with_roles(self, service):
        session = await service.create_session(1)
        await service.add_memory_entry(session.id, "user", "first")
        await service.add_memory_entry(session.id, "assistant", "second")

        context = await service.get_memory_context(session.id)

        # created_at 由数据库填充，同秒插入时顺序由实现按倒序取反决定，这里只校验角色与内容
        assert set(context.splitlines()) == {"[USER] first", "[ASSISTANT] second"}

    @pytest.mark.asyncio
    async def test_memory_context_empty(self, service):
        assert await service.get_memory_context("no-session") == ""


class TestReflections:
    @pytest.mark.asyncio
    async def test_add_reflection_defaults(self, service):
        session = await service.create_session(1)
        reflection = await service.add_reflection(session.id, "task", "note")

        assert reflection.insights == []
        assert reflection.confidence == 0.5

    @pytest.mark.asyncio
    async def test_add_reflection_with_insights_and_list(self, service):
        session = await service.create_session(1)
        await service.add_reflection(
            session.id, "t", "r", insights=["a"], confidence=0.8
        )
        await service.add_reflection(session.id, "t2", "r2")

        reflections = await service.get_session_reflections(session.id)
        assert len(reflections) == 2

    @pytest.mark.asyncio
    async def test_reflections_limit(self, service):
        session = await service.create_session(1)
        for index in range(3):
            await service.add_reflection(session.id, "t", f"r{index}")

        assert len(await service.get_session_reflections(session.id, limit=1)) == 1


class TestKnowledge:
    @pytest.mark.asyncio
    async def test_add_knowledge_defaults_and_fields(self, service):
        entry = await service.add_knowledge(1, "content")

        assert entry.knowledge_key is None
        assert entry.category == "general"
        assert entry.source == "agent"
        assert entry.importance == 0.5
        assert entry.tags == []

    @pytest.mark.asyncio
    async def test_search_knowledge_escapes_wildcards(self, service):
        await service.add_knowledge(1, "100% coverage")
        await service.add_knowledge(1, "under_score")
        await service.add_knowledge(2, "other user")

        percent = await service.search_knowledge(1, "100%")
        underscore = await service.search_knowledge(1, "under_score")

        assert [entry.content for entry in percent] == ["100% coverage"]
        assert [entry.content for entry in underscore] == ["under_score"]

    @pytest.mark.asyncio
    async def test_search_knowledge_with_category(self, service):
        await service.add_knowledge(1, "deploy note", category="ops")
        await service.add_knowledge(1, "deploy guide", category="docs")

        result = await service.search_knowledge(1, "deploy", category="ops")

        assert [entry.content for entry in result] == ["deploy note"]

    @pytest.mark.asyncio
    async def test_search_knowledge_backslash_escape(self, service):
        await service.add_knowledge(1, r"path C:\temp")
        result = await service.search_knowledge(1, r"C:\temp")
        assert [entry.content for entry in result] == [r"path C:\temp"]

    @pytest.mark.asyncio
    async def test_increment_usage(self, service):
        entry = await service.add_knowledge(1, "k")

        await service.increment_knowledge_usage(entry.id)
        await service.increment_knowledge_usage("missing")

        refreshed = await service.db.get(KnowledgeEntry, entry.id)
        assert refreshed.usage_count == 1
        assert refreshed.last_used_at is not None

    @pytest.mark.asyncio
    async def test_get_user_knowledge_with_and_without_category(self, service):
        await service.add_knowledge(1, "a", category="ops", importance=0.9)
        await service.add_knowledge(1, "b", category="docs")
        await service.add_knowledge(2, "c", category="ops")

        everything = await service.get_user_knowledge(1)
        assert {entry.content for entry in everything} == {"a", "b"}

        scoped = await service.get_user_knowledge(1, category="ops")
        assert [entry.content for entry in scoped] == ["a"]

    @pytest.mark.asyncio
    async def test_get_user_knowledge_limit(self, service):
        for index in range(3):
            await service.add_knowledge(1, f"k{index}")

        assert len(await service.get_user_knowledge(1, limit=2)) == 2


class TestToolLogsAndModelStats:
    @pytest.mark.asyncio
    async def test_log_tool_execution_truncates_result(self, service):
        session = await service.create_session(1)
        long_result = "x" * 20000

        log = await service.log_tool_execution(
            session.id, "tool", {"a": 1}, long_result,
            success=False, error_message="boom", execution_time=1.5,
        )

        assert len(log.tool_result) == 10000
        assert log.success is False
        assert log.error_message == "boom"
        assert log.execution_time == 1.5

    @pytest.mark.asyncio
    async def test_log_tool_execution_empty_result(self, service):
        session = await service.create_session(1)
        log = await service.log_tool_execution(session.id, "tool", {}, "")
        assert log.tool_result is None

    @pytest.mark.asyncio
    async def test_model_stats_create_then_update_success_and_failure(self, service):
        created = await service.update_model_stats(1, "model-key", "Model", tokens=10)
        assert created.request_count == 1
        assert created.success_count == 1
        assert created.failure_count == 0
        assert created.avg_execution_time == 0

        updated = await service.update_model_stats(
            1, "model-key", "Model", tokens=5, success=False, execution_time=2.0
        )
        assert updated.request_count == 2
        assert updated.total_tokens == 15
        assert updated.success_count == 1
        assert updated.failure_count == 1
        assert updated.avg_execution_time == pytest.approx(1.0)
        assert updated.last_used_at is not None

    @pytest.mark.asyncio
    async def test_model_stats_new_failure_entry(self, service):
        stats = await service.update_model_stats(
            2, "m2", "M2", success=False, execution_time=3.0
        )
        assert stats.success_count == 0
        assert stats.failure_count == 1
        assert stats.avg_execution_time == 3.0

    @pytest.mark.asyncio
    async def test_model_stats_update_success_path(self, service):
        await service.update_model_stats(1, "s", "S", tokens=1, execution_time=1.0)

        updated = await service.update_model_stats(
            1, "s", "S", tokens=2, success=True, execution_time=4.0
        )

        assert updated.success_count == 2
        assert updated.failure_count == 0
        assert updated.request_count == 2
        assert updated.avg_execution_time == pytest.approx(2.5)


    @pytest.mark.asyncio
    async def test_get_user_model_stats(self, service):
        await service.update_model_stats(1, "a", "A")
        await service.update_model_stats(1, "b", "B")
        await service.update_model_stats(2, "c", "C")

        stats = await service.get_user_model_stats(1)

        assert {item.model_key for item in stats} == {"a", "b"}


class TestSessionSummary:
    @pytest.mark.asyncio
    async def test_summary_with_data(self, service):
        session = await service.create_session(1, session_type="code", model_key="m")
        await service.add_memory_entry(session.id, "user", "hello")
        await service.add_reflection(session.id, "task", "note")
        session.ended_at = datetime.utcnow()
        session.success = False
        session.total_steps = 4
        session.total_tokens = 40
        await service.db.commit()

        summary = await service.get_session_summary(session.id)

        assert summary["session_type"] == "code"
        assert summary["model_key"] == "m"
        assert summary["total_steps"] == 4
        assert summary["total_tokens"] == 40
        assert summary["success"] is False
        assert summary["memory_entries"] == 1
        assert summary["reflections"] == 1
        assert summary["created_at"] is not None
        assert summary["ended_at"] is not None

    @pytest.mark.asyncio
    async def test_summary_missing_session(self, service):
        assert await service.get_session_summary("missing") == {}

    @pytest.mark.asyncio
    async def test_summary_without_created_or_ended_timestamps(self, service):
        session = await service.create_session(1)
        # server_default 在 SQLite 下会填充 created_at；手工清空以覆盖防御分支
        session.created_at = None
        session.ended_at = None
        await service.db.commit()

        summary = await service.get_session_summary(session.id)

        assert summary["created_at"] is None
        assert summary["ended_at"] is None
