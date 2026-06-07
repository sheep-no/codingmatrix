# router/guardian_router.py
import asyncio
import logging
import time
from datetime import datetime
from functools import lru_cache
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from app.utils.async_enhanced_guard import AsyncSmartGuardian
from app.utils.service_config_manager import ServiceConfigManager
from app.schema.guardian import StartGuard
from app.utils.security import verify_token
from app.utils.permissions import is_admin, is_superadmin
from app.services.resource_config import resource_config_service
from app.services.feature_switch import feature_switch_service
from app.services.log_config import log_config_service
from app.models.server_config import ServerConfig
from app.db.database import async_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/Controller")


# 单例模式 ====================

@lru_cache(maxsize=1)
def get_guardian() -> AsyncSmartGuardian:
    """
    获取 Guardian 单例实例
    
    Returns:
        AsyncSmartGuardian: 全局共享的 Guardian 实例
    """
    return AsyncSmartGuardian(check_interval=10)


# 权限验证依赖 ====================

async def require_admin(token: dict = Depends(verify_token)) -> dict:
    """
    验证 admin 及以上权限的依赖注入函数
    
    Args:
        token: JWT Token（通过 Depends 自动注入）
    
    Returns:
        dict: 验证通过后的 token
    
    Raises:
        HTTPException: 权限不足时抛出 403 错误
    """
    if not is_admin(token.get("permission_level", "")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足：需要管理员权限"
        )
    return token


async def require_superadmin(token: dict = Depends(verify_token)) -> dict:
    """
    验证 superadmin 权限的依赖注入函数（高危操作）
    
    Args:
        token: JWT Token（通过 Depends 自动注入）
    
    Returns:
        dict: 验证通过后的 token
    
    Raises:
        HTTPException: 权限不足时抛出 403 错误
    """
    if not is_superadmin(token.get("permission_level", "")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足：需要超级管理员权限"
        )
    return token

# 启动服务监控
@router.post("/guard/start")
async def start_guard(body: StartGuard, token: dict = Depends(require_superadmin)):
    """启动服务监控"""
    guardian = get_guardian()

    # 创建手动配置
    process_info = {"name": "manual", "cmdline": body.restart_cmd}
    cfg = guardian.config_manager.get_or_create_config(body.port, process_info)
    cfg.update({
        "name": body.service_name,
        "display_name": body.service_name,
        "restart_cmd": body.restart_cmd,
        "auto_start": True,
        "learned": True
    })
    guardian.config_manager.save_configs()

    # 启动监控
    asyncio.create_task(guardian.watch_port(cfg))

    return {"status": "success", "message": f"已启动监控：{body.service_name}"}


# 重命名服务
@router.put("/service/{port}/rename")
async def rename_service(port: int, process_signature: str, new_name: str, token: dict = Depends(require_superadmin)):
    """重命名服务"""
    guardian = get_guardian()
    guardian.config_manager.update_display_name(port, process_signature, new_name)
    return {"status": "success", "message": f"已重命名为：{new_name}"}


# 列出所有服务
@router.get("/services")
async def list_services(token: dict = Depends(require_admin)):
    """列出所有服务"""
    guardian = get_guardian()
    return {
        "learned": len(guardian.config_manager.configs),
        "enabled": len(guardian.config_manager.get_enabled_services()),
        "services": list(guardian.config_manager.configs.values())
    }

# 更新熔断配置
@router.put("/service/{port}/fuse-config")
async def update_fuse_config(
        port: int,
        process_signature: str,
        fuse_enabled: bool = True,
        fuse_cooldown: int = 300,
        fuse_retry_times: int = 0,
        token: dict = Depends(require_superadmin)
):
    """更新服务熔断配置"""
    guardian = get_guardian()

    key = f"{port}_{process_signature}"
    if key in guardian.config_manager.configs:
        config = guardian.config_manager.configs[key]
        config.update({
            "fuse_enabled": fuse_enabled,
            "fuse_cooldown": fuse_cooldown,
            "fuse_retry_times": fuse_retry_times,
            "fuse_retry_count": 0
        })
        guardian.config_manager.save_configs()

        # 重置运行状态
        service_name = config["name"]
        if service_name in guardian.service_state:
            guardian.service_state[service_name]["state"] = "normal"
            guardian.service_state[service_name]["fuse_retry_count"] = 0

        return {"status": "success", "config": config}

    return {"status": "error", "message": "服务配置不存在"}


# 获取熔断状态
@router.get("/service/{service_name}/fuse-status")
async def get_fuse_status(service_name: str, token: dict = Depends(require_admin)):
    """获取服务熔断状态"""
    guardian = get_guardian()

    state = guardian.service_state.get(service_name, {})
    config = next(
        (cfg for cfg in guardian.config_manager.configs.values() if cfg["name"] == service_name),
        None
    )

    if not config:
        raise HTTPException(status_code=404, detail="服务不存在")

    cooldown_remaining = 0
    if state.get("state") == "fused":
        elapsed = time.time() - state.get("last_fuse_time", 0)
        cooldown_remaining = max(0, state.get("cooldown", 0) - elapsed)

    return {
        "service_name": service_name,
        "state": state.get("state", "unknown"),
        "restart_count": guardian.restart_count.get(service_name, 0),
        "fuse_enabled": config.get("fuse_enabled"),
        "fuse_retry_count": state.get("fuse_retry_count", 0),
        "fuse_retry_times": config.get("fuse_retry_times", 0),
        "cooldown_remaining": int(cooldown_remaining),
        "config": config
    }


# 检查服务健康状态
@router.get("/health/{port}")
async def check_health(port: int, token: dict = Depends(require_admin)):
    """检查服务健康状态"""
    guardian = get_guardian()
    is_open = await guardian.is_port_open(port)
    return {
        "port": port,
        "status": "open" if is_open else "closed",
        "timestamp": datetime.now().isoformat()
    }


# ==================== 资源配置管理 API ====================

class ConfigUpdateRequest(BaseModel):
    value: str
    description: Optional[str] = None


class BatchConfigUpdateRequest(BaseModel):
    configs: Dict[str, str]


@router.get("/admin/config")
async def get_all_configs(token: dict = Depends(require_admin)):
    """
    获取所有配置

    Returns:
        所有配置项的字典
    """
    configs = await resource_config_service.get_all_configs()
    feature_status = await feature_switch_service.get_all_feature_status()

    return {
        "configs": configs,
        "feature_status": feature_status,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/admin/config/{key}")
async def get_config(key: str, token: dict = Depends(require_admin)):
    """
    获取单个配置

    Args:
        key: 配置项名称

    Returns:
        配置值
    """
    value = await resource_config_service.get_config(key)
    if value is None:
        raise HTTPException(status_code=404, detail=f"配置项不存在: {key}")

    return {
        "key": key,
        "value": value,
        "timestamp": datetime.now().isoformat()
    }


@router.put("/admin/config/{key}")
async def update_config(
    key: str,
    request: ConfigUpdateRequest,
    token: dict = Depends(require_superadmin)
):
    """
    更新单个配置

    Args:
        key: 配置项名称
        request: 配置更新请求

    Returns:
        更新结果
    """
    user_id = int(token.get("sub", 0))

    valid_keys = {
        "docker_max_memory", "docker_initial_memory", "docker_image",
        "docker_max_containers", "feature_docker_enabled",
        "feature_aicloud_enabled", "feature_project_enabled",
        "feature_workflow_enabled",
        "db_pool_size", "db_max_overflow", "db_pool_timeout",
        "log_level", "log_retention_days", "log_to_file"
    }

    if key not in valid_keys:
        raise HTTPException(
            status_code=400,
            detail=f"不允许修改的配置项: {key}"
        )

    success = await resource_config_service.set_config(
        key, request.value, user_id, request.description
    )

    if not success:
        raise HTTPException(status_code=500, detail="配置更新失败")

    if key.startswith("feature_"):
        feature_name = key.replace("feature_", "").replace("_enabled", "")
        enabled = request.value.lower() in ("true", "1", "yes", "on")
        await feature_switch_service.set_feature_enabled(feature_name, enabled, user_id)

    return {
        "status": "success",
        "key": key,
        "value": request.value,
        "timestamp": datetime.now().isoformat()
    }


@router.put("/admin/config/batch")
async def batch_update_configs(
    request: BatchConfigUpdateRequest,
    token: dict = Depends(require_superadmin)
):
    """
    批量更新配置

    Args:
        request: 配置更新请求

    Returns:
        更新结果
    """
    user_id = int(token.get("sub", 0))

    success = await resource_config_service.batch_update_configs(
        request.configs, user_id
    )

    if not success:
        raise HTTPException(status_code=500, detail="配置更新失败")

    for key, value in request.configs.items():
        if key.startswith("feature_"):
            feature_name = key.replace("feature_", "").replace("_enabled", "")
            enabled = value.lower() in ("true", "1", "yes", "on")
            await feature_switch_service.set_feature_enabled(feature_name, enabled, user_id)

    return {
        "status": "success",
        "updated_count": len(request.configs),
        "timestamp": datetime.now().isoformat()
    }


@router.get("/admin/stats")
async def get_server_stats(token: dict = Depends(require_admin)):
    """
    获取服务器资源状态

    Returns:
        服务器资源使用情况
    """
    stats = await resource_config_service.get_server_stats()
    return {
        **stats,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/admin/docker/containers")
async def list_docker_containers(token: dict = Depends(require_admin)):
    """
    获取 Docker 容器列表

    Returns:
        运行的容器列表和数量统计
    """
    try:
        import docker
        client = docker.from_env()

        containers = client.containers.list(
            filters={"label": "ai.project.validator=true"}
        )

        container_list = []
        for c in containers:
            c.reload()  # 就地更新，返回 None
            container_list.append({
                "id": c.short_id,
                "name": c.name,
                "image": c.image.tags[0] if c.image.tags else c.image.short_id,
                "status": c.status,
                "created": c.attrs.get("Created"),
                "memory_limit": c.attrs.get("HostConfig", {}).get("Memory", 0),
            })

        max_containers = await resource_config_service.get_config("docker_max_containers", "5")

        return {
            "containers": container_list,
            "running_count": len(container_list),
            "max_allowed": int(max_containers),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取容器列表失败: {str(e)}")


@router.get("/admin/ws-stats")
async def get_websocket_stats(token: dict = Depends(require_admin)):
    """
    获取 WebSocket 连接统计

    Returns:
        WebSocket 连接状态
    """
    from app.services.websocket_manager import get_ws_manager

    ws_manager = get_ws_manager()
    info = await ws_manager.get_connection_info()

    return {
        "current": info["current"],
        "max": info["max"],
        "available": info["available"],
        "timestamp": datetime.now().isoformat()
    }


@router.get("/admin/log-config")
async def get_log_config(token: dict = Depends(require_admin)):
    """
    获取日志配置

    Returns:
        当前日志配置
    """
    return log_config_service.get_config()


@router.put("/admin/log-config/level")
async def update_log_level(
    level: str,
    logger_name: str = "app",
    token: dict = Depends(require_superadmin)
):
    """
    更新日志级别

    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
        logger_name: Logger 名称，默认 app

    Returns:
        更新结果
    """
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if level.upper() not in valid_levels:
        raise HTTPException(
            status_code=400,
            detail=f"无效的日志级别: {level}，可选值: {', '.join(valid_levels)}"
        )

    user_id = int(token.get("sub", 0))

    success = log_config_service.set_log_level(logger_name, level)

    if success:
        await resource_config_service.set_config(
            "log_level", level, user_id, f"日志级别 ({logger_name})"
        )
        return {"status": "success", "level": level, "logger": logger_name}

    raise HTTPException(status_code=500, detail="更新日志级别失败")


@router.put("/admin/log-config/global-level")
async def update_global_log_level(
    level: str,
    token: dict = Depends(require_superadmin)
):
    """
    更新全局日志级别

    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)

    Returns:
        更新结果
    """
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if level.upper() not in valid_levels:
        raise HTTPException(
            status_code=400,
            detail=f"无效的日志级别: {level}，可选值: {', '.join(valid_levels)}"
        )

    user_id = int(token.get("sub", 0))

    success = log_config_service.set_global_level(level)

    if success:
        await resource_config_service.set_config(
            "log_level", level, user_id, "全局日志级别"
        )
        return {"status": "success", "level": level, "logger": "global"}

    raise HTTPException(status_code=500, detail="更新全局日志级别失败")


@router.get("/admin/memory")
async def get_memory_stats(token: dict = Depends(require_admin)):
    """
    获取详细内存统计信息

    Returns:
        内存使用详情（进程、系统、Docker 等）
    """
    import psutil
    import os

    process = psutil.Process(os.getpid())

    memory_info = process.memory_info()
    memory_full = process.memory_full_info()

    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()

    return {
        "process": {
            "rss_mb": memory_info.rss / 1024 / 1024,
            "vms_mb": memory_info.vms / 1024 / 1024,
            "uss_mb": memory_full.uss / 1024 / 1024 if hasattr(memory_full, 'uss') else 0,
            "percent": process.memory_percent()
        },
        "system": {
            "total_mb": vm.total / 1024 / 1024,
            "available_mb": vm.available / 1024 / 1024,
            "used_mb": vm.used / 1024 / 1024,
            "percent": vm.percent,
            "free_mb": vm.free / 1024 / 1024
        },
        "swap": {
            "total_mb": swap.total / 1024 / 1024,
            "used_mb": swap.used / 1024 / 1024,
            "percent": swap.percent
        },
        "recommendations": {
            "env_warning": vm.percent > 80,
            "env_critical": vm.percent > 90,
            "process_warning": process.memory_percent() > 50,
            "suggestions": _get_memory_suggestions(vm.percent, process.memory_percent())
        },
        "timestamp": datetime.now().isoformat()
    }


def _get_memory_suggestions(sys_percent: float, proc_percent: float) -> list:
    """根据内存使用情况给出优化建议"""
    suggestions = []

    if sys_percent > 90:
        suggestions.append("系统内存严重不足，建议：1) 重启服务 2) 减少 worker 数量 3) 关闭不需要的功能")
    elif sys_percent > 80:
        suggestions.append("系统内存较高，建议：1) 降低 LOG_LEVEL 2) 减少 WebSocket 连接数 3) 限制 Docker 容器数量")

    if proc_percent > 60:
        suggestions.append("进程内存占用过高，可能存在内存泄漏，建议检查")
    elif proc_percent > 40:
        suggestions.append("考虑减少 gunicorn workers 或 threads 数量")

    if not suggestions:
        suggestions.append("内存使用正常")

    return suggestions


@router.get("/admin/backup")
async def create_backup(token: dict = Depends(require_superadmin)):
    """
    创建配置文件备份

    Returns:
        备份文件路径和内容
    """
    import shutil
    import json
    from pathlib import Path

    try:
        async with async_session() as db:
            result = await db.execute(select(ServerConfig))
            configs = result.scalars().all()

            backup_data = {
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "created_by": token.get("sub"),
                "configs": {}
            }

            for config in configs:
                backup_data["configs"][config.key] = {
                    "value": config.value,
                    "description": config.description
                }

        backup_dir = Path("data/backups")
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"config_backup_{timestamp}.json"

        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)

        backup_size = backup_file.stat().st_size

        backup_list = list(backup_dir.glob("config_backup_*.json"))
        backup_list.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        older_backups = backup_list[5:]

        for old_backup in older_backups:
            old_backup.unlink()

        return {
            "status": "success",
            "message": "备份创建成功",
            "backup_file": str(backup_file),
            "backup_size": backup_size,
            "config_count": len(backup_data["configs"]),
            "download_url": f"/api/v2/Controller/admin/backup/{timestamp}"
        }

    except Exception as e:
        logger.error(f"创建备份失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建备份失败: {str(e)}")


@router.get("/admin/backup/list")
async def list_backups(token: dict = Depends(require_admin)):
    """
    列出所有备份文件
    """
    from pathlib import Path

    try:
        backup_dir = Path("data/backups")
        backup_dir.mkdir(parents=True, exist_ok=True)

        backups = []
        for backup_file in sorted(backup_dir.glob("config_backup_*.json"), reverse=True):
            stat = backup_file.stat()
            backups.append({
                "filename": backup_file.name,
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "download_url": f"/api/v2/Controller/admin/backup/download/{backup_file.name}"
            })

        return {"backups": backups}

    except Exception as e:
        logger.error(f"列出备份失败: {e}")
        raise HTTPException(status_code=500, detail=f"列出备份失败: {str(e)}")


@router.get("/admin/backup/{timestamp}")
async def download_backup(timestamp: str, token: dict = Depends(require_admin)):
    """
    下载备份文件
    """
    from pathlib import Path
    import json

    backup_file = Path(f"data/backups/config_backup_{timestamp}.json")

    if not backup_file.exists():
        raise HTTPException(status_code=404, detail="备份文件不存在")

    try:
        with open(backup_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data

    except Exception as e:
        logger.error(f"读取备份失败: {e}")
        raise HTTPException(status_code=500, detail=f"读取备份失败: {str(e)}")


@router.post("/admin/backup/restore")
async def restore_backup(
    backup_data: dict,
    token: dict = Depends(require_superadmin)
):
    """
    从备份数据恢复配置

    Args:
        backup_data: 备份数据（包含 configs 字典）
    """
    try:
        user_id = int(token.get("sub", 0))
        restored_count = 0

        async with async_session() as db:
            for key, config_data in backup_data.get("configs", {}).items():
                result = await db.execute(
                    select(ServerConfig).where(ServerConfig.key == key)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    existing.value = config_data.get("value", existing.value)
                    existing.description = config_data.get("description", existing.description)
                    existing.updated_by = user_id
                else:
                    new_config = ServerConfig(
                        key=key,
                        value=config_data.get("value", ""),
                        description=config_data.get("description", ""),
                        updated_by=user_id
                    )
                    db.add(new_config)

                restored_count += 1

            await db.commit()

        resource_config_service.invalidate_cache()

        return {
            "status": "success",
            "message": f"成功恢复 {restored_count} 项配置",
            "restored_count": restored_count
        }

    except Exception as e:
        logger.error(f"恢复备份失败: {e}")
        raise HTTPException(status_code=500, detail=f"恢复备份失败: {str(e)}")


@router.delete("/admin/backup/{filename}")
async def delete_backup(filename: str, token: dict = Depends(require_superadmin)):
    """
    删除备份文件
    """
    from pathlib import Path

    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")

    backup_file = Path(f"data/backups/{filename}")

    if not backup_file.exists():
        raise HTTPException(status_code=404, detail="备份文件不存在")

    try:
        backup_file.unlink()
        return {"status": "success", "message": "备份文件已删除"}

    except Exception as e:
        logger.error(f"删除备份失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除备份失败: {str(e)}")


class RateLimitUpdate(BaseModel):
    limit: int
    window: int


class EndpointRateLimitUpdate(BaseModel):
    endpoint: str
    limit: int
    window: int


@router.get("/admin/rate-limit")
async def get_rate_limit_config(token: dict = Depends(require_admin)):
    """
    获取限流配置
    """
    from app.middleware.rate_limiter import rate_limiter
    return rate_limiter.get_stats()


@router.put("/admin/rate-limit/global")
async def update_global_rate_limit(
    config: RateLimitUpdate,
    token: dict = Depends(require_superadmin)
):
    """
    更新全局限流配置
    """
    from app.services.rate_limit_config import rate_limit_config
    rate_limit_config.set_global_limit(config.limit, config.window)
    return {"status": "success", "config": rate_limit_config.to_dict()}


@router.put("/admin/rate-limit/ip")
async def update_ip_rate_limit(
    config: RateLimitUpdate,
    token: dict = Depends(require_superadmin)
):
    """
    更新 IP 限流配置
    """
    from app.services.rate_limit_config import rate_limit_config
    rate_limit_config.set_ip_limit(config.limit, config.window)
    return {"status": "success", "config": rate_limit_config.to_dict()}


@router.put("/admin/rate-limit/user")
async def update_user_rate_limit(
    config: RateLimitUpdate,
    token: dict = Depends(require_superadmin)
):
    """
    更新用户限流配置
    """
    from app.services.rate_limit_config import rate_limit_config
    rate_limit_config.set_user_limit(config.limit, config.window)
    return {"status": "success", "config": rate_limit_config.to_dict()}


@router.put("/admin/rate-limit/endpoint")
async def update_endpoint_rate_limit(
    config: EndpointRateLimitUpdate,
    token: dict = Depends(require_superadmin)
):
    """
    更新端点限流配置
    """
    from app.services.rate_limit_config import rate_limit_config
    rate_limit_config.set_endpoint_rule(config.endpoint, config.limit, config.window)
    return {"status": "success", "config": rate_limit_config.to_dict()}


@router.delete("/admin/rate-limit/endpoint/{endpoint}")
async def delete_endpoint_rate_limit(
    endpoint: str,
    token: dict = Depends(require_superadmin)
):
    """
    删除端点限流配置（恢复默认）
    """
    from app.services.rate_limit_config import rate_limit_config
    rate_limit_config.remove_endpoint_rule(endpoint)
    return {"status": "success", "config": rate_limit_config.to_dict()}


@router.put("/admin/rate-limit/enabled")
async def toggle_rate_limit(
    enabled: bool,
    token: dict = Depends(require_superadmin)
):
    """
    启用/禁用限流
    """
    from app.services.rate_limit_config import rate_limit_config
    rate_limit_config.set_enabled(enabled)
    return {"status": "success", "enabled": enabled}