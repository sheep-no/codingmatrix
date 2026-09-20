# app/db/permission_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.models.Permission import Permission

class PermissionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_permission(self, user_id: int, level: str) -> Permission:
        """为用户创建权限记录"""
        permission = Permission(user_id=user_id, permission_level=level)
        self.db.add(permission)
        await self.db.commit()
        await self.db.refresh(permission)
        return permission

    async def create_permission_if_not_exists(
        self, user_id: int, level: str
    ) -> Permission:
        stmt = select(Permission).where(Permission.user_id == user_id)
        result = await self.db.execute(stmt)
        permission = result.scalar_one_or_none()

        if permission:
            return permission

        try:
            return await self.create_permission(user_id, level)
        except IntegrityError:
            # 并发注册时唯一约束拦截了重复插入，回滚后返回已存在的那一行
            await self.db.rollback()
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is None:
                raise
            return existing

    async def get_permission(self, user_id: int) -> Permission | None:
        stmt = (
            select(Permission)
            .where(Permission.user_id == user_id)
            .options(selectinload(Permission.user))  # 预加载 user 关系
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
