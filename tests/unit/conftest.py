"""
Pytest 配置 - 单元测试
"""
import pytest
import asyncio
import os
import sys
from typing import AsyncGenerator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_unit.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing")
os.environ.setdefault("SILICONFLOW_API_KEY", "test-key")

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestAsyncSessionLocal = sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_tables():
    """初始化测试数据库表"""
    from app.models.base import Base
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(scope="function", autouse=True)
async def setup_database():
    """设置测试数据库"""
    await init_tables()
    yield


@pytest.fixture(scope="function")
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """创建测试数据库会话"""
    async with TestAsyncSessionLocal() as session:
        yield session
        await session.rollback()
        await session.close()


@pytest.fixture(scope="function")
async def test_user(test_db: AsyncSession):
    """创建测试用户"""
    from app.models.user import User
    from app.models.Permission import Permission

    existing = await test_db.get(User, 1)
    if existing:
        yield existing
        return

    permission = Permission(user_id=1, permission_level="normal")
    test_db.add(permission)

    user = User(
        id=1,
        username="testuser",
        email="test@example.com",
        hashed_password="$2b$12$test_hash",
    )
    test_db.add(user)

    await test_db.commit()
    await test_db.refresh(user)

    yield user

    try:
        await test_db.delete(user)
        await test_db.delete(permission)
        await test_db.commit()
    except:
        pass
