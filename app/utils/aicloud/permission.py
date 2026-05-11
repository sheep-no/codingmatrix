"""
权限检查模块

实现 aicloud 功能的权限检查：
- 检查用户是否有权限访问 aicloud
- 获取用户权限级别
"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.user import User
from app.utils.permissions import is_admin


AICLOUD_REQUIRED_PERMISSION = "admin"


async def get_user_permission_level(user_id: int, db: AsyncSession) -> str:
    """
    获取用户的权限级别

    Args:
        user_id: 用户 ID
        db: 数据库会话

    Returns:
        用户的权限级别 ("normal" / "admin" / "superadmin")
    """
    result = await db.execute(
        select(User)
        .options(selectinload(User.permission))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return "normal"

    if not user.permission:
        return "normal"

    return user.permission.permission_level or "normal"


async def check_aicloud_permission(user_id: int, db: AsyncSession) -> bool:
    """
    检查用户是否有权限访问 aicloud

    Args:
        user_id: 用户 ID
        db: 数据库会话

    Returns:
        True if user has permission, False otherwise

    Raises:
        HTTPException: 如果用户没有权限
    """
    permission_level = await get_user_permission_level(user_id, db)

    if not is_admin(permission_level):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="aicloud access requires admin permission"
        )

    return True


def require_aicloud_permission():
    """
    依赖项：获取当前用户并检查 aicloud 权限

    Usage:
        @router.post("/endpoint")
        async def endpoint(
            user_id: int = Depends(require_aicloud_permission()),
            db: AsyncSession = Depends(get_db)
        ):
            ...
    """
    async def _check_permission(
        user_id: int = None,
        db: AsyncSession = None
    ) -> int:
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not authenticated"
            )

        await check_aicloud_permission(user_id, db)
        return user_id

    return _check_permission
