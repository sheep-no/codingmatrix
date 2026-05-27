"""
健康检查 API

用于 K8s/Docker 健康检查和监控系统

端点：
- GET /api/v1/health - 基础健康检查
- GET /api/v1/health/ready - 就绪检查 (数据库连接、Redis 连接)
- GET /api/v1/health/live - 存活检查 (简单返回 200)
- GET /api/v1/health/detailed - 详细健康信息
- GET /api/v1/health/metrics - Prometheus 指标
- GET /api/v1/health/models - 模型健康状态
"""
import logging
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Response, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.health_checker import health_checker
from app.services.prometheus_metrics import generate_metrics_text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["健康检查"])

APP_VERSION = "v5.10.0"


@router.get("", summary="基础健康检查")
async def health_check():
    """
    基础健康检查

    返回:
    - status: healthy/unhealthy
    - timestamp: 检查时间
    - version: 应用版本
    """
    try:
        db_ok = await _check_db_quick()
        redis_ok = await _check_redis_quick()

        status = "healthy" if (db_ok and redis_ok) else "unhealthy"

        return {
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": APP_VERSION,
        }
    except Exception as e:
        logger.error(f"健康检查异常: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": APP_VERSION,
        }


@router.get("/ready", summary="就绪检查")
async def readiness_check():
    """
    就绪检查

    检查数据库连接和 Redis 连接
    用于 K8s readiness probe
    """
    checks = {}
    all_ready = True

    db_result = await _check_db_quick()
    checks["database"] = {"status": "connected" if db_result else "disconnected"}
    if not db_result:
        all_ready = False

    redis_result = await _check_redis_quick()
    checks["redis"] = {"status": "connected" if redis_result else "disconnected"}
    if not redis_result:
        all_ready = False

    return {
        "status": "ready" if all_ready else "not_ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


@router.get("/live", summary="存活检查")
async def liveness_check():
    """
    存活检查

    简单返回 200，用于 K8s liveness probe
    """
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _check_db_quick() -> bool:
    """快速数据库连接检查"""
    try:
        from sqlalchemy import text
        from app.db.database import async_session
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"数据库连接检查失败: {e}")
        return False


async def _check_redis_quick() -> bool:
    """快速 Redis 连接检查"""
    try:
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            return True

        from app.utils.cache import get_cache
        cache = await get_cache(redis_url)
        await cache.set("_health_check", "ok", ttl=5)
        value = await cache.get("_health_check")
        return value == "ok"
    except Exception as e:
        logger.error(f"Redis 连接检查失败: {e}")
        return False


@router.get("/detailed", summary="详细健康信息")
async def detailed_health_check():
    """
    详细健康信息

    返回完整的健康检查报告，包含所有组件的详细信息
    """
    return await health_checker.check_all()


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    """
    Prometheus 指标端点

    供外部 Prometheus 服务器定时抓取
    格式：Prometheus text exposition format
    """
    from app.services.prometheus_metrics import prometheus_metrics
    import psutil
    import gc

    prometheus_metrics.set_memory_usage(psutil.virtual_memory().used)
    prometheus_metrics.set_health_status("api", True)

    try:
        from app.services.websocket_manager import get_ws_manager
        ws_manager = get_ws_manager()
        count = await ws_manager.get_connection_count()
        prometheus_metrics.set_websocket_connections(count)
        prometheus_metrics.set_health_status("websocket", True)
    except Exception:
        prometheus_metrics.set_health_status("websocket", False)

    gc_stats = gc.get_stats()
    if gc_stats:
        collected = sum(s['collected'] for s in gc_stats)
        prometheus_metrics._registry.counter("python_gc_objects_collected", {"generation": "all"})

    text = generate_metrics_text()
    return Response(content=text, media_type="text/plain; charset=utf-8")


@router.get("/models", summary="模型健康状态")
async def model_health_check():
    """
    模型健康状态

    返回所有模型的健康指标：
    - 健康分数
    - 成功率
    - 平均延迟
    - P95 延迟
    - 队列深度
    - 状态 (healthy/degraded/circuit_breaker)
    """
    from app.agent.dynamic_model_router import get_dynamic_router

    router_instance = await get_dynamic_router()
    health_report = await router_instance.get_model_health_report()

    return {
        "status": "success",
        "models": health_report,
        "timestamp": datetime.utcnow().isoformat()
    }
