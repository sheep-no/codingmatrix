"""
性能监控 API 端点

提供性能指标查询和导出接口
"""
import logging
from fastapi import APIRouter, Depends
from app.utils.security import verify_token
from app.utils.performance_metrics import metrics_collector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/performance", tags=["性能监控"])


@router.get("", summary="获取性能指标")
async def get_performance_metrics(token: dict = Depends(verify_token)):
    """
    获取各模块的性能指标
    """
    user_id = token.get("sub", "anonymous")
    logger.info(f"性能指标查询 | user={user_id}")
    
    metrics = metrics_collector.export_metrics()
    
    return {
        "success": True,
        "metrics": metrics,
        "thresholds": metrics_collector.thresholds,
    }


@router.get("/trends", summary="获取性能趋势数据")
async def get_performance_trends(token: dict = Depends(verify_token)):
    """
    获取性能趋势数据（用于图表展示）
    """
    user_id = token.get("sub", "anonymous")
    logger.info(f"性能趋势查询 | user={user_id}")
    
    all_metrics = metrics_collector.get_all_metrics()
    
    trends = {}
    for module_name, metrics in all_metrics.items():
        trends[module_name] = {
            "avg_time_ms": metrics.avg_time_ms,
            "min_time_ms": metrics.min_time_ms if metrics.min_time_ms != float('inf') else 0,
            "max_time_ms": metrics.max_time_ms,
            "total_calls": metrics.total_calls,
            "cache_hit_rate": metrics.cache_hit_rate,
            "alerts": metrics.alerts,
        }
    
    return {
        "success": True,
        "trends": trends,
    }


@router.post("/export", summary="导出性能指标")
async def export_performance_metrics(token: dict = Depends(verify_token)):
    """
    导出性能指标到文件
    """
    user_id = token.get("sub", "anonymous")
    logger.info(f"性能指标导出 | user={user_id}")
    
    try:
        metrics_collector.save_metrics()
        return {
            "success": True,
            "message": "性能指标已导出",
        }
    except Exception as e:
        logger.error(f"性能指标导出失败：{e}")
        return {
            "success": False,
            "message": f"导出失败：{str(e)}",
        }
