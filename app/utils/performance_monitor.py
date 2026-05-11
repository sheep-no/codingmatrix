"""
性能监控中间件

监控 API 请求性能：
- 请求耗时统计
- 慢请求告警
- Prometheus 指标导出（可选）
"""
import asyncio
import logging
import time
from datetime import datetime
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# 慢请求阈值（秒）
SLOW_REQUEST_THRESHOLD = float(1.0)  # 1 秒


class PerformanceMonitorMiddleware(BaseHTTPMiddleware):
    """性能监控中间件"""

    def __init__(self, app, slow_threshold: float = SLOW_REQUEST_THRESHOLD):
        super().__init__(app)
        self.slow_threshold = slow_threshold
        self.stats: Dict[str, dict] = {}
        self._lock = asyncio.Lock()
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """处理请求并记录性能"""
        start_time = time.time()
        
        # 提取请求信息
        path = request.url.path
        method = request.method
        client_ip = request.client.host if request.client else "unknown"
        request_id = f"{datetime.utcnow().timestamp()}-{client_ip}-{path}"
        
        try:
            # 执行请求
            response = await call_next(request)
            
            # 计算耗时
            process_time = time.time() - start_time
            
            # 记录到响应头
            response.headers["X-Process-Time"] = str(round(process_time, 4))
            response.headers["X-Request-ID"] = request_id
            
            # 记录性能指标
            await self._record_metric(path, method, process_time, response.status_code)

            # 记录到 Prometheus 指标
            try:
                from app.services.prometheus_metrics import prometheus_metrics
                prometheus_metrics.record_request(method, path, response.status_code, process_time)
            except Exception:
                pass
            
            # 慢请求告警
            if process_time > self.slow_threshold:
                logger.warning(
                    f"慢请求 | method={method} | path={path} | "
                    f"time={process_time:.3f}s | status={response.status_code} | "
                    f"request_id={request_id}"
                )
            
            return response
            
        except (ValueError, TypeError, RuntimeError, OSError, KeyError) as e:
            process_time = time.time() - start_time
            logger.error(
                f"请求异常 | method={method} | path={path} | "
                f"time={process_time:.3f}s | error={str(e)}"
            )
            raise
    
    async def _record_metric(self, path: str, method: str, duration: float, status_code: int):
        """记录性能指标"""
        key = f"{method}:{path}"

        async with self._lock:
            if key not in self.stats:
                self.stats[key] = {
                    "count": 0,
                    "total_time": 0.0,
                    "min_time": float('inf'),
                    "max_time": 0.0,
                    "error_count": 0
                }

            stats = self.stats[key]
            stats["count"] += 1
            stats["total_time"] += duration
            stats["min_time"] = min(stats["min_time"], duration)
            stats["max_time"] = max(stats["max_time"], duration)

            if status_code >= 400:
                stats["error_count"] += 1

            if len(self.stats) > 1000:
                oldest_key = min(self.stats, key=lambda k: self.stats[k]["count"])
                del self.stats[oldest_key]

    async def get_stats(self) -> Dict[str, dict]:
        """获取性能统计"""
        async with self._lock:
            result = {}
            for key, stats in self.stats.items():
                if stats["count"] > 0:
                    result[key] = {
                        "count": stats["count"],
                        "avg_time": stats["total_time"] / stats["count"],
                        "min_time": stats["min_time"] if stats["min_time"] != float('inf') else 0,
                        "max_time": stats["max_time"],
                        "error_rate": stats["error_count"] / stats["count"] * 100
                    }
            return result


def setup_performance_monitoring(app, slow_threshold: float = SLOW_REQUEST_THRESHOLD):
    """
    为应用添加性能监控
    
    Args:
        app: FastAPI 应用
        slow_threshold: 慢请求阈值（秒）
    """
    app.add_middleware(PerformanceMonitorMiddleware, slow_threshold=slow_threshold)
    logger.info(f"性能监控已启用 | slow_threshold={slow_threshold}s")


# 简单的性能追踪装饰器
def track_performance(func):
    """
    追踪函数执行时间
    
    用法:
        @track_performance
        async def slow_function():
            ...
    """
    import functools
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            return await func(*args, **kwargs)
        finally:
            duration = time.time() - start_time
            if duration > 1.0:  # 超过 1 秒记录警告
                logger.warning(
                    f"慢函数 | name={func.__name__} | duration={duration:.3f}s"
                )
    
    return wrapper
