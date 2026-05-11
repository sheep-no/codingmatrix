"""动态模型路由器 - 基于延迟、成功率、队列深度的智能路由"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import deque
import logging

logger = logging.getLogger(__name__)


@dataclass
class ModelAssignment:
    """模型分配方案"""
    architect_model: str
    frontend_model: str
    backend_model: str
    reviewer_model: str
    fallback_model: str


@dataclass
class ModelMetrics:
    """模型性能指标"""
    model_name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0
    recent_latencies: deque = field(default_factory=lambda: deque(maxlen=100))
    active_requests: int = 0  # 当前队列深度
    last_error_time: Optional[float] = None
    consecutive_failures: int = 0
    last_success_time: Optional[float] = None

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests

    @property
    def avg_latency_ms(self) -> float:
        if not self.recent_latencies:
            return 0.0
        return sum(self.recent_latencies) / len(self.recent_latencies)

    @property
    def p95_latency_ms(self) -> float:
        if len(self.recent_latencies) < 5:
            return self.avg_latency_ms
        sorted_latencies = sorted(self.recent_latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def health_score(self) -> float:
        """
        计算模型健康分数 (0-100)
        权重：成功率 50%，延迟 30%，队列深度 20%
        """
        # 成功率得分 (0-50)
        success_score = self.success_rate * 50

        # 延迟得分 (0-30) - 延迟越低得分越高
        if self.avg_latency_ms == 0:
            latency_score = 30
        else:
            # 假设 10000ms 为最大可接受延迟
            latency_score = max(0, 30 * (1 - self.avg_latency_ms / 10000))

        # 队列深度得分 (0-20) - 队列越浅得分越高
        max_queue = 20
        queue_score = max(0, 20 * (1 - self.active_requests / max_queue))

        # 连续失败惩罚
        if self.consecutive_failures >= 3:
            return 0  # 熔断

        return success_score + latency_score + queue_score

    def record_success(self, latency_ms: float):
        self.total_requests += 1
        self.successful_requests += 1
        self.total_latency_ms += latency_ms
        self.recent_latencies.append(latency_ms)
        self.active_requests = max(0, self.active_requests - 1)
        self.consecutive_failures = 0
        self.last_success_time = time.time()

    def record_failure(self, error: str = ""):
        self.total_requests += 1
        self.failed_requests += 1
        self.active_requests = max(0, self.active_requests - 1)
        self.consecutive_failures += 1
        self.last_error_time = time.time()
        logger.warning(f"模型 {self.model_name} 请求失败: {error}")

    def start_request(self):
        self.active_requests += 1


class DynamicModelRouter:
    """
    动态模型路由器

    根据以下指标智能路由：
    1. 成功率 (50% 权重)
    2. 平均延迟 (30% 权重)
    3. 队列深度 (20% 权重)

    支持熔断机制：连续失败 3 次自动降级
    """

    def __init__(self):
        self._metrics: Dict[str, ModelMetrics] = {}
        self._lock = asyncio.Lock()
        self._fallback_order = [
            "Qwen/Qwen3-8B",
            "THUDM/GLM-4-9B-0414",
            "Qwen/Qwen3.5-4B"
        ]

    def get_or_create_metrics(self, model_name: str) -> ModelMetrics:
        """获取或创建模型指标（线程安全）"""
        if model_name not in self._metrics:
            self._metrics[model_name] = ModelMetrics(model_name=model_name)
        return self._metrics[model_name]

    async def record_call(self, model_name: str, success: bool, latency_ms: float, error: str = ""):
        """记录模型调用结果"""
        async with self._lock:
            metrics = self.get_or_create_metrics(model_name)
            if success:
                metrics.record_success(latency_ms)
            else:
                metrics.record_failure(error)

    async def start_call(self, model_name: str):
        """标记模型开始处理请求"""
        async with self._lock:
            metrics = self.get_or_create_metrics(model_name)
            metrics.start_request()

    async def get_best_model(self, candidate_models: List[str], task_type: str = "general") -> str:
        """
        从候选模型中选择最佳模型

        Args:
            candidate_models: 候选模型列表
            task_type: 任务类型（用于日志）

        Returns:
            最佳模型名称
        """
        if not candidate_models:
            return self._fallback_order[0]

        async with self._lock:
            # 过滤熔断的模型
            healthy_models = []
            for model_name in candidate_models:
                metrics = self.get_or_create_metrics(model_name)
                if metrics.consecutive_failures < 3:
                    healthy_models.append(model_name)

            if not healthy_models:
                # 所有模型都熔断，使用降级模型
                logger.error(f"所有候选模型都已熔断，使用降级模型: {self._fallback_order[0]}")
                return self._fallback_order[0]

            # 选择健康分数最高的模型
            best_model = max(
                healthy_models,
                key=lambda m: self.get_or_create_metrics(m).health_score
            )

            best_metrics = self.get_or_create_metrics(best_model)
            logger.info(
                f"动态路由 [{task_type}]: {best_model} "
                f"(健康分={best_metrics.health_score:.1f}, "
                f"成功率={best_metrics.success_rate:.1%}, "
                f"延迟={best_metrics.avg_latency_ms:.0f}ms, "
                f"队列={best_metrics.active_requests})"
            )

            return best_model

    async def get_model_health_report(self) -> Dict[str, Dict]:
        """获取所有模型的健康报告"""
        async with self._lock:
            report = {}
            for name, metrics in self._metrics.items():
                report[name] = {
                    "health_score": round(metrics.health_score, 2),
                    "success_rate": round(metrics.success_rate, 4),
                    "avg_latency_ms": round(metrics.avg_latency_ms, 2),
                    "p95_latency_ms": round(metrics.p95_latency_ms, 2),
                    "total_requests": metrics.total_requests,
                    "active_requests": metrics.active_requests,
                    "consecutive_failures": metrics.consecutive_failures,
                    "status": "healthy" if metrics.health_score > 70 else "degraded" if metrics.health_score > 30 else "circuit_breaker"
                }
            return report

    async def reset_metrics(self, model_name: Optional[str] = None):
        """重置指标"""
        async with self._lock:
            if model_name:
                if model_name in self._metrics:
                    del self._metrics[model_name]
            else:
                self._metrics.clear()

    def get_assignment(self, complexity) -> ModelAssignment:
        """根据复杂度获取模型分配方案"""
        return _LayeredModelRouterCompat.get_assignment(complexity)


# 全局单例
_dynamic_router: Optional[DynamicModelRouter] = None
_router_lock = asyncio.Lock()


async def get_dynamic_router() -> DynamicModelRouter:
    """获取动态路由器单例"""
    global _dynamic_router
    if _dynamic_router is None:
        async with _router_lock:
            if _dynamic_router is None:
                _dynamic_router = DynamicModelRouter()
    return _dynamic_router


# ==================== 向后兼容别名 ====================

# ModelAssignment 已在文件顶部定义

# LayeredModelRouter 是 DynamicModelRouter 的别名
LayeredModelRouter = DynamicModelRouter


# ==================== 分层模型路由（向后兼容） ====================

from app.agent.complexity import ProjectComplexity

class _LayeredModelRouterCompat:
    """分层模型路由器 - 根据复杂度分配最优模型组合（向后兼容）"""

    ASSIGNMENTS = {
        ProjectComplexity.SIMPLE: ModelAssignment(
            architect_model="Qwen/Qwen3-8B",
            frontend_model="Qwen/Qwen2.5-7B-Instruct",
            backend_model="Qwen/Qwen3-8B",
            reviewer_model="Qwen/Qwen3-8B",
            fallback_model="Qwen/Qwen3.5-4B"
        ),
        ProjectComplexity.SMALL: ModelAssignment(
            architect_model="THUDM/GLM-Z1-9B-0414",
            frontend_model="Qwen/Qwen2.5-7B-Instruct",
            backend_model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            reviewer_model="THUDM/GLM-Z1-9B-0414",
            fallback_model="Qwen/Qwen3-8B"
        ),
        ProjectComplexity.MEDIUM: ModelAssignment(
            architect_model="THUDM/GLM-Z1-9B-0414",
            frontend_model="Qwen/Qwen2.5-7B-Instruct",
            backend_model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            reviewer_model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            fallback_model="Qwen/Qwen3-8B"
        ),
        ProjectComplexity.LARGE: ModelAssignment(
            architect_model="THUDM/GLM-Z1-9B-0414",
            frontend_model="Qwen/Qwen2.5-7B-Instruct",
            backend_model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            reviewer_model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            fallback_model="Qwen/Qwen3-8B"
        ),
        ProjectComplexity.ENTERPRISE: ModelAssignment(
            architect_model="THUDM/GLM-Z1-9B-0414",
            frontend_model="Qwen/Qwen3-8B",
            backend_model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            reviewer_model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            fallback_model="Qwen/Qwen3-8B"
        ),
    }

    @classmethod
    def get_assignment(cls, complexity: ProjectComplexity) -> ModelAssignment:
        return cls.ASSIGNMENTS.get(complexity, cls.ASSIGNMENTS[ProjectComplexity.MEDIUM])


# ==================== get_model_config 工具函数 ====================

def get_model_config(model_name: str, task_type: str = "generate") -> Dict[str, Any]:
    """获取模型的最佳配置参数"""
    configs = {
        "THUDM/GLM-Z1-9B-0414": {"temperature": 0.6, "max_tokens": 8192, "thinking_budget": 4096},
        "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B": {"temperature": 0.6, "max_tokens": 8192, "thinking_budget": 4096},
        "Qwen/Qwen3.5-4B": {"temperature": 0.7, "max_tokens": 4096, "thinking_budget": 2048},
        "Qwen/Qwen3-8B": {"temperature": 0.7, "max_tokens": 4096, "thinking_budget": 2048},
        "Qwen/Qwen2.5-7B-Instruct": {"temperature": 0.7, "max_tokens": 6144, "thinking_budget": 3072},
        "THUDM/GLM-4-9B-0414": {"temperature": 0.7, "max_tokens": 6144, "thinking_budget": 3072},
    }
    return configs.get(model_name, {"temperature": 0.7, "max_tokens": 4096, "thinking_budget": 2048})


# 为 DynamicModelRouter 添加 get_model_config 类方法（向后兼容）
DynamicModelRouter.get_model_config = staticmethod(get_model_config)
LayeredModelRouter.get_model_config = staticmethod(get_model_config)
