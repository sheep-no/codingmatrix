"""
健康检查服务

提供系统各组件的健康检查功能
"""
import asyncio
import logging
import threading
import psutil
from typing import Dict, Any, Optional
from dataclasses import dataclass

from app.core.time import utcnow_naive
from app.core.version import APP_VERSION

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
        self._version = APP_VERSION
        self._start_time = utcnow_naive()

    async def check_api(self) -> HealthCheckResult:
        """检查 API 应用状态"""
        start = asyncio.get_running_loop().time()
        try:
            uptime = (utcnow_naive() - self._start_time).total_seconds()
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

            # Celery control inspect 是同步网络 RPC，直接调用会阻塞事件循环，
            # 而 /health /ready 探针调用频繁，必须放到线程中执行
            stats, active = await asyncio.to_thread(self._inspect_celery, celery_app)

            queue_size = 0
            if stats:
                for worker, info in stats.items():
                    queue_size += info.get("pool", {}).get("max-concurrency", 0)

            elapsed = (asyncio.get_running_loop().time() - start) * 1000
            if not stats:
                # broker 可达但没有 worker 响应：异步任务不会被消费，报 healthy 会掩盖
                # worker 掉线。生产编排固定带 celery 服务，缺失即异常。
                return HealthCheckResult(
                    status="degraded",
                    response_time_ms=round(elapsed, 2),
                    message="未发现可用的 Celery worker",
                    details={"workers": 0, "active_tasks": 0, "queue_size": 0}
                )
            return HealthCheckResult(
                status="healthy",
                response_time_ms=round(elapsed, 2),
                message="Celery 队列正常",
                details={
                    "workers": len(stats),
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

    @staticmethod
    def _inspect_celery(celery_app):
        """同步采集 Celery worker 状态，供 check_celery 在线程中调用"""
        inspect = celery_app.control.inspect()
        return inspect.stats(), inspect.active()

    async def check_websocket(self) -> HealthCheckResult:
        """检查 WebSocket 连接统计"""
        start = asyncio.get_running_loop().time()
        try:
            from app.services.websocket_manager import get_ws_manager
            ws_manager = get_ws_manager()
            current = ws_manager.get_connection_count()
            max_conn = ws_manager.max_connections

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

        # 各检查相互独立且多为 I/O 等待，并行执行避免探针耗时累加
        (
            api_result,
            db_result,
            redis_result,
            celery_result,
            ws_result,
            system_result,
        ) = await asyncio.gather(
            self.check_api(),
            self.check_database(),
            self.check_redis(),
            self.check_celery(),
            self.check_websocket(),
            self.check_system(),
        )

        checks["api"] = {
            "status": api_result.status,
            "response_time_ms": api_result.response_time_ms,
            "details": api_result.details
        }

        checks["database"] = {
            "status": db_result.status,
            "response_time_ms": db_result.response_time_ms,
            "message": db_result.message
        }

        checks["redis"] = {
            "status": redis_result.status,
            "response_time_ms": redis_result.response_time_ms,
            "message": redis_result.message
        }

        checks["celery"] = {
            "status": celery_result.status,
            "response_time_ms": celery_result.response_time_ms,
            "message": celery_result.message,
            "details": celery_result.details
        }

        checks["websocket"] = {
            "status": ws_result.status,
            "response_time_ms": ws_result.response_time_ms,
            "message": ws_result.message,
            "details": ws_result.details
        }

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
            "timestamp": utcnow_naive().isoformat(),
            "checks": checks,
            "version": self._version
        }

    async def check_ready(self) -> Dict[str, Any]:
        """就绪检查（用于 K8s readiness probe）"""
        checks = {}
        all_ready = True

        # 三项检查相互独立，并行执行避免就绪探针延迟叠加
        db_result, redis_result, system_result = await asyncio.gather(
            self.check_database(),
            self.check_redis(),
            self.check_system(),
        )

        checks["database"] = {
            "status": db_result.status,
            "message": db_result.message,
            "response_time_ms": db_result.response_time_ms,
        }
        if db_result.status != "healthy":
            all_ready = False

        checks["redis"] = {
            "status": redis_result.status,
            "message": redis_result.message,
            "response_time_ms": redis_result.response_time_ms,
        }
        if redis_result.status not in ("healthy", "skipped"):
            all_ready = False

        checks["system"] = {
            "status": system_result.status,
            "details": system_result.details,
        }
        if system_result.status == "unhealthy":
            all_ready = False

        return {
            "status": "ready" if all_ready else "not_ready",
            "timestamp": utcnow_naive().isoformat(),
            "checks": checks,
        }

    async def check_live(self) -> Dict[str, Any]:
        """存活检查（用于 K8s liveness probe）"""
        return {
            "status": "alive",
            "timestamp": utcnow_naive().isoformat()
        }


_health_checker_instance: Optional[HealthChecker] = None
_health_checker_lock = threading.Lock()


def get_health_checker() -> HealthChecker:
    """获取健康检查器单例"""
    global _health_checker_instance
    if _health_checker_instance is None:
        with _health_checker_lock:
            if _health_checker_instance is None:
                _health_checker_instance = HealthChecker()
    return _health_checker_instance


health_checker = get_health_checker()
