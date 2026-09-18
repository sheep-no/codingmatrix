"""删除用户时的级联清理回归测试（MD1）。
复现问题：History/File/Task 在 ORM 层未声明级联，aicloud 系列与 github 配置
外键没有 ondelete，aicloud 知识库与 db/models 历史表 user_id 是裸列。删除用户
时前者触发 NOT NULL 报错，后者残留孤儿数据。
"""

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.db.models as db_models  # noqa: F401  注册 db 层历史表
from app.models.base import Base


@pytest.mark.asyncio
async def test_delete_user_purges_all_owned_rows(tmp_path, monkeypatch):
    from app.api.v2 import user_manage
    from app.models.Permission import Permission
    from app.models.aicloud import (
        AicloudAuditLog,
        AicloudMessage,
        AicloudReview,
        AicloudSession,
    )
    from app.models.aicloud_knowledge import AicloudKnowledgeChunk, AicloudKnowledgeDoc
    from app.models.agent_memory import AgentSession, ToolExecutionLog
    from app.models.file import File
    from app.models.github_config import GithubUserConfig
    from app.models.history import History
    from app.models.task import Task
    from app.models.unified_state import Message, Session
    from app.models.user import User

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'delete_user.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    async def _noop(*args, **kwargs):
        return None

    # 缓存失效依赖真实 Redis，聚焦数据库级联行为
    monkeypatch.setattr(user_manage, "invalidate_user_cache", _noop)
    monkeypatch.setattr(user_manage, "invalidate_cache_by_prefix", _noop)

    async with session_factory() as db:
        victim = User(username="victim", email="victim@example.com", hashed_password="x")
        keeper = User(username="keeper", email="keeper@example.com", hashed_password="x")
        db.add_all([victim, keeper])
        await db.flush()
        victim_id, keeper_id = victim.id, keeper.id

        for owner in (victim_id, keeper_id):
            db.add(Permission(user_id=owner, permission_level="normal"))
            db.add(History(user_id=owner, conversation_id=1, prompt="p", response="r"))
            db.add(File(filename=f"f{owner}.txt", file_path=f"/tmp/f{owner}", file_size=1, user_id=owner))
            db.add(Task(task_id=f"task-{owner}", task_type="file_process", user_id=owner))
            db.add(GithubUserConfig(user_id=owner))
            db.add(AicloudSession(id=f"as-{owner}", user_id=owner))
            db.add(AicloudMessage(session_id=f"as-{owner}", role="user", content="hi"))
            db.add(AicloudReview(id=f"ar-{owner}", operation_type="upload", file_path="/tmp/x", requested_by=owner))
            db.add(AicloudAuditLog(user_id=owner, operation="op", status="ok"))
            db.add(AicloudKnowledgeDoc(id=f"kd-{owner}", user_id=owner, filename="k.txt"))
            db.add(AicloudKnowledgeChunk(id=f"kc-{owner}", doc_id=f"kd-{owner}", user_id=owner, content="c", chunk_index=0))
            db.add(AgentSession(id=f"ags-{owner}", user_id=owner))
            db.add(db_models.ProjectSession(session_id=f"ps-{owner}", user_id=str(owner), requirement="req"))
            db.add(db_models.WorkflowHistory(workflow_id=f"wf-{owner}", user_id=str(owner), request="req"))
            db.add(db_models.ImageGenerationHistory(image_id=f"img-{owner}", user_id=str(owner), prompt="p"))
            db.add(db_models.ConversationMessage(session_id=f"cm-{owner}", user_id=str(owner), role="user", content="c"))
        # unified_state 的 Session/Message 无 ORM 关系，需保证会话先落库
        await db.flush()
        for owner in (victim_id, keeper_id):
            db.add(Session(id=f"us-{owner}", user_id=owner, module="m"))
        await db.flush()
        for owner in (victim_id, keeper_id):
            db.add(ToolExecutionLog(session_id=f"ags-{owner}", tool_name="t"))
        await db.flush()
        for owner in (victim_id, keeper_id):
            db.add(Message(session_id=f"us-{owner}", user_id=owner, sequence=1, role="user", content="c"))
        await db.commit()

        await user_manage.delete_user(
            user_id=victim_id,
            db=db,
            token={"sub": str(keeper_id), "permission_level": "superadmin"},
        )

        async def count(model, **filters):
            stmt = select(func.count()).select_from(model)
            for column, value in filters.items():
                stmt = stmt.where(getattr(model, column) == value)
            return (await db.execute(stmt)).scalar_one()

        assert await count(User, id=victim_id) == 0
        assert await count(Permission, user_id=victim_id) == 0
        assert await count(History, user_id=victim_id) == 0
        assert await count(File, user_id=victim_id) == 0
        assert await count(Task, user_id=victim_id) == 0
        assert await count(GithubUserConfig, user_id=victim_id) == 0
        assert await count(AicloudSession, user_id=victim_id) == 0
        assert await count(AicloudMessage, session_id=f"as-{victim_id}") == 0
        assert await count(AicloudReview, requested_by=victim_id) == 0
        assert await count(AicloudAuditLog, user_id=victim_id) == 0
        assert await count(AicloudKnowledgeDoc, user_id=victim_id) == 0
        assert await count(AicloudKnowledgeChunk, user_id=victim_id) == 0
        assert await count(AgentSession, user_id=victim_id) == 0
        assert await count(ToolExecutionLog, session_id=f"ags-{victim_id}") == 0
        # 仅依赖 DB ondelete=CASCADE 的表也应被清理
        assert await count(Session, user_id=victim_id) == 0
        assert await count(Message, user_id=victim_id) == 0
        assert await count(db_models.ProjectSession, user_id=str(victim_id)) == 0
        assert await count(db_models.WorkflowHistory, user_id=str(victim_id)) == 0
        assert await count(db_models.ImageGenerationHistory, user_id=str(victim_id)) == 0
        assert await count(db_models.ConversationMessage, user_id=str(victim_id)) == 0

        # 其他用户的数据不受影响
        assert await count(User, id=keeper_id) == 1
        assert await count(Permission, user_id=keeper_id) == 1
        assert await count(History, user_id=keeper_id) == 1
        assert await count(File, user_id=keeper_id) == 1
        assert await count(Task, user_id=keeper_id) == 1
        assert await count(GithubUserConfig, user_id=keeper_id) == 1
        assert await count(AicloudSession, user_id=keeper_id) == 1
        assert await count(AicloudMessage, session_id=f"as-{keeper_id}") == 1
        assert await count(AicloudReview, requested_by=keeper_id) == 1
        assert await count(AicloudAuditLog, user_id=keeper_id) == 1
        assert await count(AicloudKnowledgeDoc, user_id=keeper_id) == 1
        assert await count(AicloudKnowledgeChunk, user_id=keeper_id) == 1
        assert await count(AgentSession, user_id=keeper_id) == 1
        assert await count(ToolExecutionLog, session_id=f"ags-{keeper_id}") == 1
        assert await count(Session, user_id=keeper_id) == 1
        assert await count(Message, user_id=keeper_id) == 1
        assert await count(db_models.ProjectSession, user_id=str(keeper_id)) == 1
        assert await count(db_models.WorkflowHistory, user_id=str(keeper_id)) == 1
        assert await count(db_models.ImageGenerationHistory, user_id=str(keeper_id)) == 1
        assert await count(db_models.ConversationMessage, user_id=str(keeper_id)) == 1

    await engine.dispose()
