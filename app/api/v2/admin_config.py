from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.utils.security import verify_token, require_superadmin
from app.utils.system_config import system_config_manager
from pydantic import BaseModel
from typing import Optional, Any

router = APIRouter(prefix="/admin", tags=["Admin"])

class UserLimitUpdate(BaseModel):
    user_id: str
    limit: int
    tier: Optional[str] = "custom"

class ConfigUpdate(BaseModel):
    path: str
    value: Any

@router.post("/user-limit")
async def update_user_concurrent_limit(
    update: UserLimitUpdate,
    token: dict = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """更新用户并发项目限制（超级管理员权限）"""
    try:
        system_config_manager.update_user_override(
            update.user_id, 
            update.limit, 
            update.tier
        )
        return {
            "success": True,
            "message": f"用户 {update.user_id} 并发限制已更新为 {update.limit}",
            "user_id": update.user_id,
            "limit": update.limit,
            "tier": update.tier
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/user-limit/{user_id}")
async def remove_user_concurrent_limit(
    user_id: str,
    token: dict = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """移除用户并发项目限制覆盖（超级管理员权限）"""
    try:
        system_config_manager.remove_user_override(user_id)
        return {
            "success": True,
            "message": f"用户 {user_id} 并发限制覆盖已移除",
            "user_id": user_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/config")
async def update_system_config(
    update: ConfigUpdate,
    token: dict = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """更新系统配置（超级管理员权限）"""
    try:
        system_config_manager.set_config_value(update.path, update.value)
        return {
            "success": True,
            "message": f"配置 {update.path} 已更新",
            "path": update.path,
            "value": update.value
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/config")
async def get_system_config(
    token: dict = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """获取系统配置（超级管理员权限）"""
    return system_config_manager._config


class SandboxConfigUpdate(BaseModel):
    enable_code_sandbox: Optional[bool] = None
    sandbox_languages: Optional[str] = None


@router.get("/sandbox-config")
async def get_sandbox_config(token: dict = Depends(require_superadmin)):
    """获取代码沙箱配置"""
    from app.core.config import settings
    return {
        "enable_code_sandbox": settings.ENABLE_CODE_SANDBOX,
        "sandbox_languages": [l.strip() for l in settings.SANDBOX_LANGUAGES.split(",")],
    }


@router.put("/sandbox-config")
async def update_sandbox_config(
    update: SandboxConfigUpdate,
    token: dict = Depends(require_superadmin)
):
    """更新代码沙箱配置（超级管理员权限）"""
    import os
    changes = []
    if update.enable_code_sandbox is not None:
        os.environ["ENABLE_CODE_SANDBOX"] = str(update.enable_code_sandbox).lower()
        changes.append(f"enable_code_sandbox={update.enable_code_sandbox}")
    if update.sandbox_languages is not None:
        os.environ["SANDBOX_LANGUAGES"] = update.sandbox_languages
        changes.append(f"sandbox_languages={update.sandbox_languages}")

    if not changes:
        raise HTTPException(status_code=400, detail="未提供任何配置更新")

    # 更新 system_config_manager
    if update.enable_code_sandbox is not None:
        system_config_manager.set_config_value("enable_code_sandbox", update.enable_code_sandbox)
    if update.sandbox_languages is not None:
        system_config_manager.set_config_value("sandbox_languages", update.sandbox_languages)

    return {
        "success": True,
        "message": f"沙箱配置已更新: {', '.join(changes)}",
        "restart_required": True,
    }