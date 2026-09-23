"""
SystemConfigManager - 系统配置管理器

负责管理用户并发限制、会话管理配置等系统级设置
支持管理员动态更新配置
"""

import json
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from app.core.config import BASE_DIR

logger = logging.getLogger(__name__)

class SystemConfigManager:
    _instance = None
    # __new__ 是同步方法，用线程锁保护首次构造
    _instance_lock = threading.Lock()
    # save_config 可能在多线程（管理员热更新）并发触发
    _config_lock = threading.RLock()
    _config: Dict[str, Any] = {}
    # 锚定仓库根而非进程 CWD：否则从不同工作目录启动会读写不同配置文件
    _config_file: Path = BASE_DIR / "configs" / "system_config.json"
    
    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self.load_config()
            from app.utils.dynamic_concurrent import ConcurrentLimitManager
            self.concurrent_mgr = ConcurrentLimitManager()
    
    def load_config(self):
        """加载系统配置"""
        try:
            if self._config_file.exists():
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                logger.info(f"系统配置加载成功: {self._config_file}")
            else:
                logger.warning(f"系统配置文件不存在，使用默认配置: {self._config_file}")
                self._config = self._get_default_config()
                self.save_config()
        except Exception as e:
            logger.error(f"加载系统配置失败: {e}")
            self._config = self._get_default_config()
    
    def save_config(self):
        """保存系统配置"""
        with self._config_lock:
            try:
                self._config_file.parent.mkdir(parents=True, exist_ok=True)
                self._config["system_config"]["last_updated"] = datetime.now().isoformat()
                with open(self._config_file, 'w', encoding='utf-8') as f:
                    json.dump(self._config, f, ensure_ascii=False, indent=2)
                logger.info("系统配置保存成功")
            except Exception as e:
                logger.error(f"保存系统配置失败: {e}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认系统配置"""
        return {
            "system_config": {
                "version": "1.0",
                "last_updated": datetime.now().isoformat(),
                "health_aware_routing": {
                    "enabled": False,
                    "system_overload_threshold": 0.8,
                    "model_load_weight": 0.6,
                    "system_load_weight": 0.4,
                    "max_concurrent_requests": 100
                }
            },
            "user_concurrent_limits": {
                "role_defaults": {
                    "free": 1,
                    "basic": 2, 
                    "premium": 5,
                    "enterprise": 10,
                    "superadmin": 50
                },
                "user_overrides": {}
            },
            "session_management": {
                "cleanup_enabled": True,
                "max_active_sessions": 100,
                "idle_timeout_minutes": 30
            },
            "ppt_generation": {
                "max_slides": 50,
                "supported_templates": ["modern", "business", "creative", "minimal", "academic", "tech", "education", "medical", "elegant"]
            }
        }
    
    def get_user_concurrent_limit(self, user_id: str, user_role: str = "free") -> int:
        """获取用户的并发项目限制"""
        sys_limits = self._config.get("system_config", {}).get("user_concurrent_limits", {})
        top_limits = self._config.get("user_concurrent_limits", {})

        # 检查用户覆盖配置（update_user_override 写入 system_config 内，兼容顶层旧结构）
        overrides = sys_limits.get("user_overrides") or top_limits.get("user_overrides") or {}
        if user_id in overrides:
            return overrides[user_id].get("limit", 1)

        # 根据用户角色获取限制
        # _get_default_config 用顶层 role_defaults，既有部署文件用 system_config 内 default_tiers
        default_tiers = (
            top_limits.get("role_defaults")
            or sys_limits.get("role_defaults")
            or sys_limits.get("default_tiers")
            or top_limits.get("default_tiers")
            or {}
        )
        return default_tiers.get(user_role, default_tiers.get("free", 1))
    
    async def get_active_sessions_for_user(self, user_id: str) -> list:
        """获取用户的活跃会话列表（查询 DB 中 status=running 的会话）"""
        try:
            from app.db.database import async_session
            from app.db.models import ProjectSession
            from sqlalchemy import select

            async with async_session() as db:
                result = await db.execute(
                    select(ProjectSession).where(
                        ProjectSession.user_id == int(user_id),
                        ProjectSession.status == "running"
                    ).order_by(ProjectSession.created_at.desc())
                )
                sessions = result.scalars().all()
                return [s.to_dict() for s in sessions]
        except Exception as e:
            logger.error(f"获取用户活跃会话失败: {e}")
            return []
    
    def can_create_new_session(self, user_id: str, user_role: str = "free") -> bool:
        """检查用户是否可以创建新会话"""
        return self.concurrent_mgr.can_create_session(user_role)

    async def update_concurrent_limit(self, role: str, new_limit: int, changed_by: str, reason: str = ""):
        """热更新并发限制（v4.8.0，无需重启）"""
        return await self.concurrent_mgr.update_limit(role, new_limit, changed_by, reason)

    def get_concurrent_limit(self, role: str) -> int:
        """获取当前并发限制"""
        return self.concurrent_mgr.get_limit(role)

    def get_limit_change_history(self, limit: int = 50):
        """获取限制变更历史"""
        return self.concurrent_mgr.get_change_history(limit)
    
    def update_user_override(self, user_id: str, limit: int, tier: str = "custom"):
        """更新用户覆盖配置（管理员权限）"""
        overrides = self._config.setdefault("system_config", {}).setdefault("user_concurrent_limits", {}).setdefault("user_overrides", {})
        overrides[user_id] = {"limit": limit, "tier": tier}
        self.save_config()
    
    def remove_user_override(self, user_id: str):
        """移除用户覆盖配置（管理员权限）"""
        overrides = self._config.get("system_config", {}).get("user_concurrent_limits", {}).get("user_overrides", {})
        if user_id in overrides:
            del overrides[user_id]
            self.save_config()
    
    def get_config_value(self, path: str, default=None):
        """获取配置值，支持点分隔路径"""
        keys = path.split('.')
        value = self._config
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def set_config_value(self, path: str, value):
        """设置配置值，支持点分隔路径（管理员权限）"""
        keys = path.split('.')
        config = self._config
        for key in keys[:-1]:
            config = config.setdefault(key, {})
        config[keys[-1]] = value
        self.save_config()

# 全局实例
system_config_manager = SystemConfigManager()
