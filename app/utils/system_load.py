"""
系统负载监控 - 提供系统负载快照接口供路由器和 Orchestrator 使用
"""
import asyncio
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass

from app.core.graceful_shutdown import GracefulShutdownManager
from app.middleware.rate_limiter import RateLimitMiddleware
from app.core.config import settings


@dataclass
class SystemLoadSnapshot:
    """系统负载快照"""
    timestamp: float
    active_requests: int  # 活跃请求数
    is_drain_mode: bool  # Drain 模式状态
    model_queue_depths: Dict[str, int]  # 各模型队列深度
    rate_limit_stats: Dict[str, Any]  # 限流统计
    system_resources: Dict[str, float]  # 系统资源使用率


class SystemLoadMonitor:
    """
    系统负载监控器
    
    提供系统负载快照接口，从 graceful_shutdown、中间件层等采集数据，
    供 dynamic_model_router 和 orchestrator 调用。
    """
    
    def __init__(self):
        try:
            self.shutdown_manager = GracefulShutdownManager.get_instance()
        except AttributeError:
            # Fallback: create a new instance directly
            self.shutdown_manager = GracefulShutdownManager()
        self.last_snapshot: Optional[SystemLoadSnapshot] = None
        self.snapshot_cache_ttl = 1.0  # 快照缓存 TTL (秒)
        self._last_snapshot_time = 0.0
    
    async def get_load_snapshot(self, force_refresh: bool = False) -> SystemLoadSnapshot:
        """
        获取系统负载快照
        
        Args:
            force_refresh: 是否强制刷新（忽略缓存）
            
        Returns:
            系统负载快照
        """
        current_time = time.time()
        
        # 使用缓存避免频繁计算
        if (not force_refresh and 
            self.last_snapshot is not None and 
            current_time - self._last_snapshot_time < self.snapshot_cache_ttl):
            return self.last_snapshot
        
        # 采集活跃请求数（需要从中间件或请求上下文获取）
        active_requests = await self._get_active_requests()
        
        # 获取 Drain 模式状态
        is_drain_mode = self.shutdown_manager.is_draining()
        
        # 获取各模型队列深度（需要从 executor 或模型路由器获取）
        model_queue_depths = await self._get_model_queue_depths()
        
        rate_limit_stats = await self._get_rate_limit_stats()
        
        # 获取系统资源使用率
        system_resources = await self._get_system_resources()
        
        snapshot = SystemLoadSnapshot(
            timestamp=current_time,
            active_requests=active_requests,
            is_drain_mode=is_drain_mode,
            model_queue_depths=model_queue_depths,
            rate_limit_stats=rate_limit_stats,
            system_resources=system_resources
        )
        
        self.last_snapshot = snapshot
        self._last_snapshot_time = current_time
        
        return snapshot
    
    async def _get_rate_limit_stats(self) -> Dict[str, Any]:
        try:
            from app.middleware.rate_limiter import rate_limiter as middleware_limiter
            return middleware_limiter.get_stats()
        except Exception:
            return {}

    async def _get_active_requests(self) -> int:
        try:
            from app.middleware.rate_limiter import rate_limiter as middleware_limiter
            current_time = time.time()
            global_limit, global_window = middleware_limiter._config.global_limit
            global_key = f"global:{int(current_time / global_window)}"
            with middleware_limiter._lock:
                middleware_limiter._cleanup_old_records(global_key, current_time - global_window)
                return len(middleware_limiter._history[global_key])
        except Exception:
            return 0
    
    async def _get_model_queue_depths(self) -> Dict[str, int]:
        depths: Dict[str, int] = {}
        try:
            from app.celery_app import celery_app
            inspect = celery_app.control.inspect(timeout=2.0)
            if inspect:
                active = inspect.active() or {}
                reserved = inspect.reserved() or {}
                for worker_tasks in active.values():
                    for task in worker_tasks:
                        model = "default"
                        args = task.get("args")
                        if args and isinstance(args, (list, tuple)) and len(args) > 0:
                            params = args[0] if isinstance(args[0], dict) else {}
                            model = params.get("model", params.get("language", "default"))
                        depths[model] = depths.get(model, 0) + 1
                for worker_tasks in reserved.values():
                    for task in worker_tasks:
                        model = "default"
                        args = task.get("args")
                        if args and isinstance(args, (list, tuple)) and len(args) > 0:
                            params = args[0] if isinstance(args[0], dict) else {}
                            model = params.get("model", params.get("language", "default"))
                        depths[model] = depths.get(model, 0) + 1
        except Exception:
            pass
        return depths
    
    async def _get_system_resources(self) -> Dict[str, float]:
        """
        获取系统资源使用率
        
        Returns:
            {'cpu': 0.5, 'memory': 0.7, 'disk': 0.3}
        """
        try:
            import psutil
            
            cpu_percent = psutil.cpu_percent() / 100.0
            memory_percent = psutil.virtual_memory().percent / 100.0
            disk_percent = psutil.disk_usage('/').percent / 100.0
            
            return {
                'cpu': cpu_percent,
                'memory': memory_percent,
                'disk': disk_percent
            }
        except ImportError:
            # 如果没有 psutil，返回默认值
            return {'cpu': 0.0, 'memory': 0.0, 'disk': 0.0}
    
    def is_system_overloaded(self, threshold: float = 0.8) -> bool:
        """
        判断系统是否过载
        
        Args:
            threshold: 过载阈值（0.0-1.0）
            
        Returns:
            是否过载
        """
        if self.last_snapshot is None:
            return False
        
        # 检查 CPU、内存、磁盘使用率
        resources = self.last_snapshot.system_resources
        if any(value > threshold for value in resources.values()):
            return True

        max_active = settings.MAX_ACTIVE_REQUESTS
        try:
            from app.utils.resource_guard import get_resource_guard
            safe_concurrency = get_resource_guard().get_safe_concurrency()
            max_active = max(max_active, safe_concurrency * 25)
        except Exception:
            pass
        if self.last_snapshot.active_requests > max_active:
            return True
        
        return False
    
    def get_model_load_score(self, model_name: str) -> float:
        """
        获取模型负载评分（0.0-1.0，越低越好）
        
        Args:
            model_name: 模型名称
            
        Returns:
            负载评分
        """
        if self.last_snapshot is None:
            return 0.5
        
        # 基础评分基于队列深度
        queue_depth = self.last_snapshot.model_queue_depths.get(model_name, 0)
        queue_score = min(queue_depth / 10.0, 1.0)  # 假设10为高负载
        
        # 系统资源影响
        resource_score = max(self.last_snapshot.system_resources.values())
        
        # 综合评分
        return (queue_score * 0.7 + resource_score * 0.3)


# 全局系统负载监控器实例
system_load_monitor = SystemLoadMonitor()