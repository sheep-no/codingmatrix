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
from typing import Dict, Optional

from app.utils.logging import generate_request_id, set_request_context

logger = logging.getLogger(__name__)


# 慢请求阈值（秒）
SLOW_REQUEST_THRESHOLD = float(1.0)  # 1 秒


class PerformanceMonitorMiddleware:
    """性能监控中间件（纯 ASGI 实现）

    为什么不用 BaseHTTPMiddleware（与 logging.py 的 RequestLoggingMiddleware 一致）:
    - BaseHTTPMiddleware 用 anyio TaskGroup 包装 call_next，并缓冲响应体
    - 流式响应（SSE 等）会被整体缓冲，失去流式效果
    - 客户端断开时 cancel scope 会传播到下游 await，干扰 session 清理
    """

    def __init__(self, app, slow_threshold: float = SLOW_REQUEST_THRESHOLD):
        self.app = app
        self.slow_threshold = slow_threshold
        self.stats: Dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        method = scope.get("method", "")
        path = scope.get("path", "")
        # 与 RequestLoggingMiddleware 共用同一个 request_id：本中间件在最外层，
        # 先生成并写入上下文，内层日志中间件复用之，避免响应头 X-Request-ID
        # 与日志中的 request_id 对不上导致追踪断裂。
        request_id = generate_request_id()
        set_request_context(request_id)

        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                # 去掉下游（RequestLoggingMiddleware）已写入的同名头，避免重复
                headers = [
                    (k, v) for (k, v) in message.get("headers", [])
                    if k.lower() not in (b"x-request-id", b"x-process-time")
                ]
                headers.append((b"x-process-time", str(round(time.time() - start_time, 4)).encode()))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except (ValueError, TypeError, RuntimeError, OSError, KeyError) as e:
            process_time = time.time() - start_time
            logger.error(
                f"请求异常 | method={method} | path={path} | "
                f"time={process_time:.3f}s | error={str(e)}"
            )
            raise

        process_time = time.time() - start_time

        # 指标标签使用路由模板，带参路径会把 UUID/ID 带进 label 造成高基数
        metric_path = self._metric_path(scope)

        # 记录性能指标
        await self._record_metric(metric_path, method, process_time, status_code)

        # 记录到 Prometheus 指标
        try:
            from app.services.prometheus_metrics import prometheus_metrics
            prometheus_metrics.record_request(method, metric_path, status_code, process_time)
        except Exception:
            pass

        # 慢请求告警
        if process_time > self.slow_threshold:
            logger.warning(
                f"慢请求 | method={method} | path={path} | "
                f"time={process_time:.3f}s | status={status_code} | "
                f"request_id={request_id}"
            )

    @staticmethod
    def _metric_path(scope) -> str:
        """返回用于指标标签的路径。

        已匹配路由取路由模板（如 /items/{item_id}），使同一端点的不同参数
        归并到同一指标；未匹配路由统一归为 <unmatched>，避免被任意路径扫描
        撑爆指标基数。
        """
        route = scope.get("route")
        route_path = getattr(route, "path", None)
        return route_path or "<unmatched>"
    
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
