"""
功能开关服务

管理功能模块的启用/禁用状态
"""
import logging
from typing import Optional, Dict
from app.services.resource_config import resource_config_service

logger = logging.getLogger(__name__)


class FeatureSwitchService:
    """
    功能开关服务

    管理功能模块的启用/禁用状态
    """

    FEATURE_KEYS = {
        "docker": "feature_docker_enabled",
        "aicloud": "feature_aicloud_enabled",
        "project": "feature_project_enabled",
        "workflow": "feature_workflow_enabled",
    }

    FEATURE_NAMES = {
        "docker": "Docker 功能",
        "aicloud": "AI Cloud 功能",
        "project": "项目生成功能",
        "workflow": "工作流功能",
    }

    _instance: Optional["FeatureSwitchService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

    async def is_feature_enabled(self, feature: str) -> bool:
        """
        检查功能是否启用

        Args:
            feature: 功能名称 (docker/aicloud/project/workflow)

        Returns:
            是否启用
        """
        config_key = self.FEATURE_KEYS.get(feature)
        if not config_key:
            logger.warning(f"未知的功能名称: {feature}")
            return False

        value = await resource_config_service.get_config(config_key, "true")
        return value.lower() in ("true", "1", "yes", "on")

    async def set_feature_enabled(
        self,
        feature: str,
        enabled: bool,
        user_id: Optional[int] = None
    ) -> bool:
        """
        设置功能启用/禁用

        Args:
            feature: 功能名称
            enabled: 是否启用
            user_id: 操作人 ID

        Returns:
            是否成功
        """
        config_key = self.FEATURE_KEYS.get(feature)
        if not config_key:
            logger.warning(f"未知的功能名称: {feature}")
            return False

        value = "true" if enabled else "false"
        success = await resource_config_service.set_config(
            config_key, value, user_id
        )

        if success:
            feature_name = self.FEATURE_NAMES.get(feature, feature)
            status = "启用" if enabled else "禁用"
            logger.info(f"功能开关已更新 | {feature_name} -> {status} | user_id={user_id}")

        return success

    async def get_all_feature_status(self) -> Dict[str, bool]:
        """
        获取所有功能的状态

        Returns:
            功能状态字典
        """
        result = {}
        for feature in self.FEATURE_KEYS.keys():
            result[feature] = await self.is_feature_enabled(feature)
        return result

    async def check_access(self, feature: str) -> tuple[bool, Optional[str]]:
        """
        检查功能访问权限

        Args:
            feature: 功能名称

        Returns:
            (是否允许访问, 错误消息)
        """
        if await self.is_feature_enabled(feature):
            return True, None

        feature_name = self.FEATURE_NAMES.get(feature, feature)
        return False, f"{feature_name}已关闭，请联系管理员"


feature_switch_service = FeatureSwitchService()
