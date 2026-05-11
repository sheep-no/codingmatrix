"""
SystemConfigManager - 系统配置管理器

负责管理用户并发限制、会话管理配置等系统级设置
支持管理员动态更新配置
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class SystemConfigManager:
    _instance = None
    _config: Dict[str, Any] = {}
    _config_file: Path = Path("./configs/system_config.json")
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self.load_config()
    
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
        try:
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            self._config["system_config"]["last_updated"] = datetime.now().isoformat()
            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
            logger.info("系统配置保存成功")
        except Exception as e:
            logger.error(f"保存系统配置失败: {e}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "system_config": {
                "version": "1.0",
                "last_updated": datetime.now().isoformat(),
                "user_concurrent_limits": {
                    "default_tiers": {
                        "free": 1,
                        "basic": 2,
                        "premium": 5,
                        "enterprise": 10,
                        "superadmin": 50
                    },
                    "user_overrides": {}
                },
                "session_management": {
                    "cleanup_inactive_after_hours": 24,
                    "max_sessions_per_user": 10,
                    "auto_cleanup_enabled": True
                },
                "project_generation": {
                    "enabled": True,
                    "max_concurrent_per_user": 1
                },
                "ppt_generation": {
                    "enabled": True,
                    "max_slides_per_presentation": 50,
                    "supported_templates": ["modern", "classic", "creative", "business", "academic"],
                    "preview_enabled": True,
                    "export_formats": ["pptx", "pdf", "html"]
                }
            }
        }
    
    def get_user_concurrent_limit(self, user_id: str, user_role: str = "free") -> int:
        """获取用户的并发项目限制"""
        # 检查用户覆盖配置
        overrides = self._config.get("system_config", {}).get("user_concurrent_limits", {}).get("user_overrides", {})
        if user_id in overrides:
            return overrides[user_id].get("limit", 1)
        
        # 根据用户角色获取限制
        default_tiers = self._config.get("system_config", {}).get("user_concurrent_limits", {}).get("default_tiers", {})
        return default_tiers.get(user_role, default_tiers.get("free", 1))
    
    def get_active_sessions_for_user(self, user_id: str) -> list:
        """获取用户的活跃会话列表（需要与会话管理器集成）"""
        try:
            from app.agent.session_manager import SessionManager
            sm = SessionManager()
            sessions = sm.get_user_sessions(user_id)
            return [asdict(session) for session in sessions]
        except Exception as e:
            logger.error(f"获取用户活跃会话失败: {e}")
            return []
    
    def can_create_new_session(self, user_id: str, user_role: str = "free") -> bool:
        """检查用户是否可以创建新会话"""
        limit = self.get_user_concurrent_limit(user_id, user_role)
        active_sessions = self.get_active_sessions_for_user(user_id)
        return len(active_sessions) < limit
    
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