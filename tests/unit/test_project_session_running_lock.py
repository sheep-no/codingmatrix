"""每用户仅一行 running 会话的部分唯一索引（FRESCAN-10 跨 worker 兜底）"""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.ai_agent.helpers import _create_project_session
from app.db.models import ProjectSession
from app.models.base import Base


@pytest.fixture
async def db_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _make_session(session_id: str, user_id: str, status: str = "running") -> ProjectSession:
    return ProjectSession(
        session_id=session_id,
        user_id=user_id,
        requirement="req",
        output_dir=None,
        status=status,
    )


@pytest.mark.asyncio
async def test_same_user_second_running_row_is_rejected(db_factory):
    async with db_factory() as db:
        db.add(_make_session("s1", "u1"))
        await db.commit()

        db.add(_make_session("s2", "u1"))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

        result = await db.execute(
            select(ProjectSession).where(ProjectSession.user_id == "u1", ProjectSession.status == "running")
        )
        assert result.scalar_one_or_none().session_id == "s1"


@pytest.mark.asyncio
async def test_different_users_each_keep_one_running_row(db_factory):
    async with db_factory() as db:
        db.add(_make_session("s1", "u1"))
        db.add(_make_session("s2", "u2"))
        await db.commit()

        result = await db.execute(
            select(ProjectSession).where(ProjectSession.status == "running")
        )
        assert len(result.scalars().all()) == 2


@pytest.mark.asyncio
async def test_terminal_rows_do_not_block_new_running_session(db_factory):
    async with db_factory() as db:
        db.add(_make_session("s1", "u1", status="completed"))
        db.add(_make_session("s2", "u1", status="failed"))
        db.add(_make_session("s3", "u1", status="cancelled"))
        await db.commit()

        db.add(_make_session("s4", "u1"))
        await db.commit()

        result = await db.execute(
            select(ProjectSession).where(
                ProjectSession.user_id == "u1", ProjectSession.status == "running"
            )
        )
        assert result.scalar_one_or_none().session_id == "s4"


@pytest.mark.asyncio
async def test_status_transition_frees_the_running_slot(db_factory):
    async with db_factory() as db:
        db.add(_make_session("s1", "u1"))
        await db.commit()

        result = await db.execute(
            select(ProjectSession).where(ProjectSession.session_id == "s1")
        )
        session = result.scalar_one()
        session.status = "completed"
        await db.commit()

        db.add(_make_session("s2", "u1"))
        await db.commit()

        result = await db.execute(
            select(ProjectSession).where(
                ProjectSession.user_id == "u1", ProjectSession.status == "running"
            )
        )
        assert result.scalar_one_or_none().session_id == "s2"


@pytest.mark.asyncio
async def test_create_helper_converts_conflict_to_409(db_factory):
    async with db_factory() as db:
        db.add(_make_session("s1", 1))
        await db.commit()

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await _create_project_session(db, 1, "s2", "req", None)
        assert exc_info.value.status_code == 409

        result = await db.execute(
            select(ProjectSession).where(ProjectSession.session_id == "s2")
        )
        assert result.scalar_one_or_none() is None
