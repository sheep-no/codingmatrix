"""Permission.user_id 唯一约束回归测试（models.md MD2）。
User.permission 声明为 uselist=False，同一用户出现多行权限会让读取抛
MultipleResultsFound，因此在模型层为 user_id 增加唯一约束。
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base


@pytest.mark.asyncio
async def test_permission_user_id_is_unique(tmp_path):
    from app.models.Permission import Permission
    from app.models.user import User

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'permission.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as db:
        user = User(username="dup", email="dup@example.com", hashed_password="x")
        db.add(user)
        await db.flush()

        db.add(Permission(user_id=user.id, permission_level="normal"))
        await db.commit()

        db.add(Permission(user_id=user.id, permission_level="admin"))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

    await engine.dispose()
