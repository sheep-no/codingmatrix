"""
健康检查服务

提供系统各组件的健康检查功能
"""
import asyncio
import logging
import psutil
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    status: str
    response_time_ms: float = 0
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class HealthChecker:
    """
    健康检查服务

    检查项：
    - API 应用状态
    - 数据库连接
    - Redis 连接（如果启用）
    - Celery 队列状态
    - WebSocket 连接统计
    - 系统资源（磁盘、内存）
    """

    def __init__(self):
        self._version = "v3.0"
        self._start_time = datetime.utcnow()

    async def check_api(self) -> HealthCheckResult:
        """检查 API 应用状态"""
        start = asyncio.get_running_loop().time()
        try:
            uptime = (datetime.utcnow() - self._start_time).total_seconds()
            elapsed = (asyncio.get_running_loop().time() - start) * 1000
            return HealthCheckResult(
                status="healthy",
                response_time_ms=round(elapsed, 2),
                message="API 服务正常运行",
                details={
                    "version": self._version,
                    "uptime_seconds": round(uptime, 2)
                }
            )
        except Exception as e:
            elapsed = (asyncio.get_running_loop().time() - start) * 1000
            return HealthCheckResult(
                status="unhealthy",
                response_time_ms=round(elapsed, 2),
                message=str(e)
            )

    async def check_database(self) -> HealthCheckResult:
        """检查数据库连接"""
        start = asyncio.get_running_loop().time()
        try:
            from sqlalchemy import text
            from app.db.database import async_session
            async with async_session() as db:
                await db.execute(text("SELECT 1"))
            elapsed = (asyncio.get_running_loop().time() - start) * 1000
            return HealthCheckResult(
                status="healthy",
                response_time_ms=round(elapsed, 2),
                message="数据库连接正常"
            )
        except Exception as e:
            elapsed = (asyncio.get_running_loop().time() - start) * 1000
            logger.error(f"数据库健康检查失败: {e}")
            return HealthCheckResult(
                status="unhealthy",
                response_time_ms=round(elapsed, 2),
                message=f"数据库连接失败: {str(e)}"
            )

    async def check_redis(self) -> HealthCheckResult:
        """检查 Redis 连接"""
        start = asyncio.get_running_loop().time()
        try:
            import os
            redis_url = os.getenv("REDIS_URL")
            if not redis_url:
                return HealthCheckResult(
                    status="skipped",
                    response_time_ms=0,
                    message="Redis 未配置"
                )

            from app.utils.cache import get_cache
            cache = await get_cache(redis_url)
            await cache.set("health_check", "ok", ttl=10)
            value = await cache.get("health_check")
            if value != "ok":
                raise Exception("Redis 读写验证失败")

            elapsed = (asyncio.get_running_loop().time() - start) * 1000
            return HealthCheckResult(
                status="healthy",
                response_time_ms=round(elapsed, 2),
                message="Redis 连接正常"
            )
        except Exception as e:
            elapsed = (asyncio.get_running_loop().time() - start) * 1000
            logger.error(f"Redis 健康检查失败: {e}")
            return HealthCheckResult(
                status="unhealthy",
                response_time_ms=round(elapsed, 2),
                message=f"Redis 连接失败: {str(e)}"
            )

    async def check_celery(self) -> HealthCheckResult:
        """检查 Celery 队列状态"""
        start = asyncio.get_running_loop().time()
        try:
            from app.celery_app import celery_app
            if not celery_app:
                return HealthCheckResult(
                    status="skipped",
                    response_time_ms=0,
                    message="Celery 未配置"
                )

            inspect = celery_app.control.inspect()
            stats = inspect.stats()
            active = inspect.active()

            queue_size = 0
            if stats:
                for worker, info in stats.items():
                    queue_size += info.get("pool", {}).get("max-concurrency", 0)

            elapsed = (asyncio.get_running_loop().time() - start) * 1000
            return HealthCheckResult(
                status="healthy",
                response_time_ms=round(elapsed, 2),
                message="Celery 队列正常",
                details={
                    "workers": len(stats) if stats else 0,
                    "active_tasks": sum(len(tasks) for tasks in (active or {}).values()),
                    "queue_size": queue_size
                }
            )
        except Exception as e:
            elapsed = (asyncio.get_running_loop().time() - start) * 1000
            logger.warning(f"Celery 健康检查失败: {e}")
            return HealthCheckResult(
                status="degraded",
                response_time_ms=round(elapsed, 2),
                message=f"Celery 检查失败: {str(e)}"
            )

    async def check_websocket(self) -> HealthCheckResult:
        """检查 WebSocket 连接统计"""
        start = asyncio.get_running_loop().time()
        try:
            from app.services.websocket_manager import get_ws_manager
            ws_manager = get_ws_manager()
            current = ws_manager.get_connection_count()
            max_conn = ws_manager._max_connections

            elapsed = (asyncio.get_running_loop().time() - start) * 1000
            return HealthCheckResult(
                status="healthy",
                response_time_ms=round(elapsed, 2),
                message="WebSocket 服务正常",
                details={
                    "current": current,
                    "max": max_conn,
                    "available": max_conn - current
                }
            )
        except Exception as e:
            elapsed = (asyncio.get_running_loop().time() - start) * 1000
            logger.error(f"WebSocket 健康检查失败: {e}")
            return HealthCheckResult(
                status="unhealthy",
                response_time_ms=round(elapsed, 2),
                message=f"WebSocket 检查失败: {str(e)}"
            )

    async def check_system(self) -> HealthCheckResult:
        """检查系统资源"""
        start = asyncio.get_running_loop().time()
        try:
            disk = psutil.disk_usage("/")
            memory = psutil.virtual_memory()

            disk_free_gb = round(disk.free / (1024 ** 3), 2)
            memory_percent = memory.percent

            status = "healthy"
            if memory_percent > 90 or disk.free < 1024 ** 3:
                status = "unhealthy"
            elif memory_percent > 75 or disk.free < 5 * 1024 ** 3:
                status = "degraded"

            elapsed = (asyncio.get_running_loop().time() - start) * 1000
            return HealthCheckResult(
                status=status,
                response_time_ms=round(elapsed, 2),
                message="系统资源正常",
                details={
                    "disk_free_gb": disk_free_gb,
                    "disk_percent": round(disk.percent, 1),
                    "memory_percent": round(memory_percent, 1),
                    "memory_available_mb": round(memory.available / (1024 ** 2), 2)
                }
            )
        except Exception as e:
            elapsed = (asyncio.get_running_loop().time() - start) * 1000
            logger.error(f"系统资源检查失败: {e}")
            return HealthCheckResult(
                status="unhealthy",
                response_time_ms=round(elapsed, 2),
                message=f"系统资源检查失败: {str(e)}"
            )

    async def check_all(self) -> Dict[str, Any]:
        """执行所有健康检查"""
        checks = {}

        api_result = await self.check_api()
        checks["api"] = {
            "status": api_result.status,
            "response_time_ms": api_result.response_time_ms,
            "details": api_result.details
        }

        db_result = await self.check_database()
        checks["database"] = {
            "status": db_result.status,
            "response_time_ms": db_result.response_time_ms,
            "message": db_result.message
        }

        redis_result = await self.check_redis()
        checks["redis"] = {
            "status": redis_result.status,
            "response_time_ms": redis_result.response_time_ms,
            "message": redis_result.message
        }

        celery_result = await self.check_celery()
        checks["celery"] = {
            "status": celery_result.status,
            "response_time_ms": celery_result.response_time_ms,
            "message": celery_result.message,
            "details": celery_result.details
        }

        ws_result = await self.check_websocket()
        checks["websocket"] = {
            "status": ws_result.status,
            "response_time_ms": ws_result.response_time_ms,
            "message": ws_result.message,
            "details": ws_result.details
        }

        system_result = await self.check_system()
        checks["system"] = {
            "status": system_result.status,
            "response_time_ms": system_result.response_time_ms,
            "details": system_result.details
        }

        overall_status = "healthy"
        if any(c["status"] == "unhealthy" for c in checks.values()):
            overall_status = "unhealthy"
        elif any(c["status"] == "degraded" for c in checks.values()):
            overall_status = "degraded"

        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": checks,
            "version": self._version
        }

    async def check_ready(self) -> Dict[str, Any]:
        """就绪检查（用于 K8s readiness probe）"""
        checks = {}
        all_ready = True

        db_result = await self.check_database()
        checks["database"] = {
            "status": db_result.status,
            "message": db_result.message,
            "response_time_ms": db_result.response_time_ms,
        }
        if db_result.status != "healthy":
            all_ready = False

        redis_result = await self.check_redis()
        checks["redis"] = {
            "status": redis_result.status,
            "message": redis_result.message,
            "response_time_ms": redis_result.response_time_ms,
        }
        if redis_result.status not in ("healthy", "skipped"):
            all_ready = False

        system_result = await self.check_system()
        checks["system"] = {
            "status": system_result.status,
            "details": system_result.details,
        }
        if system_result.status == "unhealthy":
            all_ready = False

        return {
            "status": "ready" if all_ready else "not_ready",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": checks,
        }

    async def check_live(self) -> Dict[str, Any]:
        """存活检查（用于 K8s liveness probe）"""
        return {
            "status": "alive",
            "timestamp": datetime.utcnow().isoformat()
        }


_health_checker_instance: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """获取健康检查器单例"""
    global _health_checker_instance
    if _health_checker_instance is None:
        _health_checker_instance = HealthChecker()
    return _health_checker_instance


health_checker = get_health_checker()
