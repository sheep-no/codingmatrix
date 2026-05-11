from fastapi import APIRouter, Query, Depends, HTTPException,status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from sqlalchemy.orm import joinedload

from app.models.Permission import Permission
from app.models.user import User
from app.utils.security import verify_token, hash_password, validate_password_strength
from app.utils.permissions import is_admin, is_superadmin

from app.db.database import get_db
from app.schema.manageUser import *
from app.utils.cache import invalidate_user_cache
from app.utils.cache_decorator import invalidate_cache_by_prefix
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# 辅助函数 ====================

async def _get_user_with_permission(db: AsyncSession, user_id: int):
    """
    获取用户及其权限信息（带异常处理）
    
    Args:
        db: 数据库会话
        user_id: 用户 ID
    
    Returns:
        User: 用户对象
    
    Raises:
        HTTPException: 用户不存在时抛出 404
    """
    result = await db.execute(
        select(User).options(joinedload(User.permission)).where(User.id == user_id)
    )
    user = result.scalar()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


@router.get("/Controller/users", response_model=UserListResponse,
             summary="分页查询用户列表")
async def get_users(
        page: int = Query(1, ge=1, description="页码从1开始"),
        page_size: int = Query(10, ge=1, le=100, description="每页数据量，最大为100"),
        keyword: Optional[str] = Query(None, description="搜素关键词"),
        permission_level: Optional[str] = Query(None, pattern="^(normal|admin|superadmin)$", description="权限筛选"),
        sort_by: str = Query("created_at", pattern="^(id|username|email|created_at)$", description="排序字段"),
        sort_order: str = Query("desc", pattern="^(asc|desc)$", description="排序方向"),
        db: AsyncSession = Depends(get_db),
        token: dict = Depends(verify_token)
):
    """
    获取用户列表（支持分页、搜索、筛选、排序）
    - 权限要求：super
    - 用户名可重复，邮箱唯一
    """
    # 权限检查（admin 和 superadmin 都可以管理用户）
    if not is_admin(token.get("permission_level", "")):
        raise HTTPException(status_code=403, detail="需要管理员权限")

    logger.info(f"管理员查询用户列表 | admin={token['sub']} | page={page} | page_size={page_size} | keyword={keyword or 'None'}")
    query = (select(User, Permission).outerjoin
             (Permission, User.id == Permission.user_id))
    if keyword:
        query = query.where(User.username.contains(keyword)
                            | User.email.contains(keyword))
    if permission_level:
        query = query.where(Permission.permission_level == permission_level)
    sort_column = {
        "id": User.id,
        "username": User.username,
        "email": User.email,
        "created_at": User.created_at
    }[sort_by]
    query = query.order_by(sort_column.desc()
                           if sort_order == "desc" else
                           sort_column.asc()
                           )
    count_query = select(func.count()).select_from(
        query.subquery()
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    rows = result.fetchall()
    users = []
    for user, permission in rows:
        users.append({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "permission_level": permission.permission_level if permission
            else "",
            "created_at": str(user.created_at)
        })
    return {
        "total": total,
        "users": users,
        "page": page,
        "page_size": page_size
    }


@router.post("/Controller/create_user", response_model=UserResponse,
             summary="创建新用户")
async def create_user(
        body: UserCreateRequest,
        db: AsyncSession = Depends(get_db),
        token: dict = Depends(verify_token)

):
    """
        创建新用户
        - 权限要求：super
        - 用户名可重复，邮箱唯一
        - 会自动创建关联的 Permission 记录
    """
    if not is_admin(token.get("permission_level", "")):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    # 验证密码强度
    is_valid, message = validate_password_strength(body.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)
    
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar():
        raise HTTPException(status_code=400, detail="邮箱已存在")
    hashed_password = hash_password(body.password)
    new_user = User(
        username=body.username,
        email=body.email,
        hashed_password=hashed_password
    )
    db.add(new_user)
    await db.flush()
    new_permission = Permission(
        user_id=new_user.id,
        permission_level=body.permission_level,
    )
    db.add(new_permission)
    await db.commit()
    await db.refresh(new_user)
    logger.info(f"管理员创建用户 | admin={token['sub']} | user={new_user.username}({new_user.id})")
    return {
        "id": new_user.id,
        "username": new_user.username,
        "email": new_user.email,
        "permission_level": body.permission_level,
        "created_at": str(new_user.created_at),
    }


@router.patch("/Controller/update_user/{user_id}",
              response_model=UserResponse, summary="更改用户信息")
async def update_user(
        user_id: int,
        body: UserUpdateRequest,
        db: AsyncSession = Depends(get_db),
        token: dict = Depends(verify_token)
):
    """
    更新用户信息
    - 权限要求：super
    - 不能修改当前登录用户
    - 邮箱唯一性检查（排除自己）
    """
    if not is_admin(token.get("permission_level", "")):
        raise HTTPException(status_code=403, detail="需要管理员权限")

    if user_id == int(token["sub"]):
        raise HTTPException(status_code=400, detail="不能修改当前登录用户")
    
    # 使用辅助函数获取用户
    user: User = await _get_user_with_permission(db, user_id)
    if body.username is not None:
        await db.execute(
            update(User).where(User.id == user_id).values(username=body.username)
        )
    if body.email is not None:
        result=await db.execute(
            select(User)
            .where(User.email == body.email, User.id != user_id)
        )
        if result.scalar():
            raise HTTPException(status_code=400, detail="邮箱已存在")
        await db.execute(update(User).
                         where(User.id == user_id).
                         values(email=body.email))
    if body.permission_level is not None:
        # 确保 Permission 记录存在
        if not user.permission:
            user.permission = Permission(user_id=user_id, permission_level="normal")
            db.add(user.permission)
            await db.flush()

        # 更新权限
        await db.execute(
            update(Permission).where(Permission.user_id == user_id).values(
                permission_level=body.permission_level
            )
        )

    await db.commit()
    await db.refresh(user)
    if user.permission:
        await db.refresh(user.permission)
    
    if body.email:
        await invalidate_user_cache(body.email)
    
    try:
        await invalidate_cache_by_prefix("profile")
    except Exception as e:
        logger.warning(f"用户缓存失效失败: {e}")
    
    logger.info(f"管理员更新用户 | admin={token['sub']} | user_id={user_id}")
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "permission_level": user.permission.permission_level if user.permission else "normal",
        "created_at": str(user.created_at),
    }


@router.delete("/Controller/delete_user/{user_id}",
               status_code=status.HTTP_204_NO_CONTENT, summary="删除用户")
async def delete_user(
        user_id:int,
        db:AsyncSession=Depends(get_db),
        token:dict=Depends(verify_token)
):
    """
        删除用户
        - 权限要求：super
        - 不能删除当前登录用户
        - 会级联删除 Permission 和关联的聊天记录
    """
    if not is_admin(token.get("permission_level", "")):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    if user_id == int(token['sub']):
        raise HTTPException(status_code=400, detail="不能删除当前登录用户")
    
    # 使用辅助函数获取用户
    user = await _get_user_with_permission(db, user_id)
    await db.execute(delete(Permission).where(Permission.user_id==user_id))
    await db.delete(user)
    await db.commit()
    await invalidate_user_cache(user.email)
    
    try:
        await invalidate_cache_by_prefix("profile")
    except Exception as e:
        logger.warning(f"用户缓存失效失败: {e}")
    
    logger.info(f"管理员删除用户 | admin={token['sub']} | user_id={user_id}")
    return {"detail": "用户已删除"}


@router.post("/Controller/{user_id}/reset-password", summary="重置用户密码")
async def reset_password(
        user_id:int,
        body:ResetPasswordRequest,
        db:AsyncSession=Depends(get_db),
        token:dict=Depends(verify_token)
):
    if not is_admin(token.get("permission_level", "")):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    await db.execute(
        update(User).where(User.id == user_id).values(
            hashed_password=hash_password(body.new_password)
        )
    )
    await db.commit()
    await invalidate_user_cache(user.email)
    
    try:
        await invalidate_cache_by_prefix("profile")
    except Exception as e:
        logger.warning(f"用户缓存失效失败: {e}")
    
    logger.info(f"管理员重置密码 | admin={token['sub']} | user_id={user_id}")
    return {"detail": "密码已重置，请通知用户重新登录"}