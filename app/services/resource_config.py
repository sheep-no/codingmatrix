"""
资源配置服务

提供服务器配置和资源监控的统一接口
"""
import asyncio
import logging
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.server_config import ServerConfig, ServerStats
from app.db.database import async_session

logger = logging.getLogger(__name__)


class ResourceConfigService:
    """
    资源配置服务

    管理服务器配置项和资源监控数据
    """

    _instance: Optional["ResourceConfigService"] = None
    _lock_conf = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._config_cache: Dict[str, str] = {}
        self._cache_loaded = False
        self._cache_lock = asyncio.Lock()

    async def _ensure_cache_loaded(self, db: AsyncSession):
        """确保配置缓存已加载"""
        if self._cache_loaded:
            return

        async with self._cache_lock:
            if self._cache_loaded:
                return

            result = await db.execute(select(ServerConfig))
            configs = result.scalars().all()

            self._config_cache = {c.key: c.value for c in configs}

            for key, default_info in ServerConfig.DEFAULT_CONFIGS.items():
                if key not in self._config_cache:
                    self._config_cache[key] = default_info["value"]

                    new_config = ServerConfig(
                        key=key,
                        value=default_info["value"],
                        description=default_info["description"]
                    )
                    db.add(new_config)

            await db.commit()
            self._cache_loaded = True

    async def get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        获取配置值

        Args:
            key: 配置项名称
            default: 默认值

        Returns:
            配置值或默认值
        """
        if key in self._config_cache:
            return self._config_cache[key]

        async with async_session() as db:
            await self._ensure_cache_loaded(db)
            return self._config_cache.get(key, default)

    async def set_config(
        self,
        key: str,
        value: str,
        user_id: Optional[int] = None,
        description: Optional[str] = None
    ) -> bool:
        """
        设置配置值

        Args:
            key: 配置项名称
            value: 配置值
            user_id: 更新人 ID
            description: 配置描述

        Returns:
            是否成功
        """
        async with async_session() as db:
            await self._ensure_cache_loaded(db)

            result = await db.execute(
                select(ServerConfig).where(ServerConfig.key == key)
            )
            config = result.scalar_one_or_none()

            if config:
                config.value = value
                if user_id:
                    config.updated_by = user_id
            else:
                config = ServerConfig(
                    key=key,
                    value=value,
                    description=description or "",
                    updated_by=user_id
                )
                db.add(config)

            await db.commit()
            self._config_cache[key] = value

            logger.info(f"配置已更新 | key={key} | value={value} | user_id={user_id}")
            return True

    async def get_all_configs(self) -> Dict[str, Any]:
        """
        获取所有配置

        Returns:
            配置字典
        """
        async with async_session() as db:
            await self._ensure_cache_loaded(db)

            result = {}
            for key, value in self._config_cache.items():
                result[key] = value
            return result

    async def batch_update_configs(
        self,
        configs: Dict[str, str],
        user_id: Optional[int] = None
    ) -> bool:
        """
        批量更新配置

        Args:
            configs: 配置字典
            user_id: 更新人 ID

        Returns:
            是否成功
        """
        async with async_session() as db:
            for key, value in configs.items():
                result = await db.execute(
                    select(ServerConfig).where(ServerConfig.key == key)
                )
                config = result.scalar_one_or_none()

                if config:
                    config.value = value
                    if user_id:
                        config.updated_by = user_id
                else:
                    default_desc = ServerConfig.DEFAULT_CONFIGS.get(key, {}).get("description", "")
                    config = ServerConfig(
                        key=key,
                        value=value,
                        description=default_desc,
                        updated_by=user_id
                    )
                    db.add(config)

                self._config_cache[key] = value

            await db.commit()
            logger.info(f"批量配置已更新 | count={len(configs)} | user_id={user_id}")
            return True

    async def get_server_stats(self) -> Dict[str, Any]:
        """
        获取服务器资源状态

        Returns:
            资源状态字典
        """
        import psutil

        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        docker_count = await self._get_docker_container_count()
        max_containers = int(
            await self.get_config("docker_max_containers", "5")
        )

        stats = {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory": {
                "total": memory.total,
                "used": memory.used,
                "percent": memory.percent,
                "available": memory.available
            },
            "disk": {
                "total": disk.total,
                "used": disk.used,
                "percent": disk.percent
            },
            "docker": {
                "running": docker_count,
                "max_allowed": max_containers
            }
        }

        return stats

    async def _get_docker_container_count(self) -> int:
        """
        获取当前运行的 Docker 容器数量

        Returns:
            容器数量
        """
        try:
            import docker
            client = docker.from_env()
            return len(client.containers.list())
        except Exception as e:
            logger.warning(f"获取 Docker 容器数量失败: {e}")
            return 0

    def invalidate_cache(self):
        """使配置缓存失效"""
        self._cache_loaded = False
        self._config_cache.clear()


resource_config_service = ResourceConfigService()
