"""动态模型路由器 - 基于延迟、成功率、队列深度的智能路由（支持全局健康感知）"""

import asyncio
import json
import os
import random
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import deque
import logging

from app.utils.system_load import system_load_monitor

logger = logging.getLogger(__name__)

# Agent 模型配置文件路径
AGENT_MODEL_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../../data/agent_model_config.json")

# 模型 ID 到模型 Key 的映射（从 model_registry 同步）
MODEL_ID_TO_KEY = {
    "deepseek-r1": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
    "qwen2.5-7b": "Qwen/Qwen2.5-7B-Instruct",
    "qwen3-8b": "Qwen/Qwen3-8B",
    "qwen3.5-4b": "Qwen/Qwen3.5-4B",
    "glm-z1-9b": "THUDM/GLM-Z1-9B-0414",
    "glm-4-9b": "THUDM/GLM-4-9B-0414",
    "glm-4.1v-9b": "THUDM/GLM-4.1V-9B-Thinking",
    "deepseek-ocr": "deepseek-ai/DeepSeek-OCR",
    "kolors": "Kwai-Kolors/Kolors",
    "bce-embedding": "netease-youdao/bce-embedding-base_v1",
    "bge-large-zh": "BAAI/bge-large-zh-v1.5",
    "bge-m3": "BAAI/bge-m3",
    "bge-reranker-v2-m3": "BAAI/bge-reranker-v2-m3",
    "bce-reranker": "netease-youdao/bce-reranker-base_v1",
    "hunyuan-mt": "tencent/Hunyuan-MT-7B",
}

# 模型 Key 到模型 ID 的反向映射
MODEL_KEY_TO_ID = {v: k for k, v in MODEL_ID_TO_KEY.items()}


def resolve_model_key(model_id_or_key: str) -> str:
    """将模型 ID 或模型 Key 统一转换为模型 Key

    支持两种格式：
    - 模型 ID: "qwen3-8b" (registry 中的 ID)
    - 模型 Key: "Qwen/Qwen3-8B" (API 调用时使用的名称)
    """
    # 如果已经是完整的模型 Key 格式，直接返回
    if "/" in model_id_or_key:
        return model_id_or_key
    # 否则尝试从 ID 映射到 Key
    return MODEL_ID_TO_KEY.get(model_id_or_key, model_id_or_key)


def load_agent_model_config() -> Optional[Dict[str, Any]]:
    """从配置文件加载 Agent 模型配置"""
    try:
        if os.path.exists(AGENT_MODEL_CONFIG_PATH):
            with open(AGENT_MODEL_CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"已加载 Agent 模型配置: {AGENT_MODEL_CONFIG_PATH}")
                return config
    except Exception as e:
        logger.warning(f"加载 Agent 模型配置失败: {e}")
    return None


def save_agent_model_config(config: Dict[str, Any]) -> bool:
    """保存 Agent 模型配置到文件"""
    try:
        os.makedirs(os.path.dirname(AGENT_MODEL_CONFIG_PATH), exist_ok=True)
        with open(AGENT_MODEL_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info(f"已保存 Agent 模型配置: {AGENT_MODEL_CONFIG_PATH}")
        return True
    except Exception as e:
        logger.error(f"保存 Agent 模型配置失败: {e}")
        return False


class _NoopLock:
    """空操作锁 — 用于数据库自身已处理并发控制的场景"""
    def acquire(self, blocking=True): return True
    def release(self): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass


class ModelPerformanceTracker:

    DB_PATH = "/tmp/model_performance.db"
    MAX_DB_SIZE_BYTES = 1 * 1024 * 1024
    RETENTION_DAYS = 30

    def __init__(self, db_path: Optional[str] = None, sync_lock_factory=None):
        self.DB_PATH = db_path or self.__class__.DB_PATH
        self._conn = sqlite3.connect(self.DB_PATH, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._write_lock = asyncio.Lock()
        # sync_lock_factory: 可替换的同步锁工厂，默认 threading.Lock
        # 传入 _NoopLock 可跳过锁（适用于数据库自带并发控制的场景）
        self._sync_lock = (sync_lock_factory or threading.Lock)()
        # 跨上下文互斥锁：防止 async 和 sync 同时操作同一 sqlite 连接
        # 任何路径操作数据库前必须获取此锁，确保 asyncio.Lock 和 threading.Lock 互斥
        self._cross_context_lock = threading.Lock()
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS performance ("
            "model_name TEXT NOT NULL, "
            "task_type TEXT NOT NULL, "
            "success_rate REAL NOT NULL DEFAULT 0.0, "
            "avg_latency REAL NOT NULL DEFAULT 0.0, "
            "total_calls INTEGER NOT NULL DEFAULT 0, "
            "consecutive_failures INTEGER NOT NULL DEFAULT 0, "
            "last_updated REAL NOT NULL, "
            "PRIMARY KEY (model_name, task_type))"
        )
        self._conn.commit()
        self._cleanup()

    def _cleanup(self):
        cutoff = time.time() - self.RETENTION_DAYS * 86400
        self._conn.execute(
            "DELETE FROM performance WHERE last_updated < ?", (cutoff,)
        )
        self._conn.commit()
        try:
            db_size = 0
            cursor = self._conn.execute(
                "SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()"
            )
            row = cursor.fetchone()
            if row:
                db_size = row[0]
            if db_size > self.MAX_DB_SIZE_BYTES:
                self._conn.execute(
                    "DELETE FROM performance WHERE last_updated < ?",
                    (time.time() - 7 * 86400,)
                )
                self._conn.commit()
                self._conn.execute("VACUUM")
        except Exception as e:
            logger.debug(f"模型路由操作失败：{e}")

    async def record_call(self, model: str, task_type: str, success: bool, latency: float):
        now = time.time()
        # 在线程池中执行，避免 threading.Lock 阻塞事件循环
        await asyncio.to_thread(self._record_call_sync, model, task_type, success, latency)

    def _record_call_sync(self, model: str, task_type: str, success: bool, latency: float):
        """同步版本 record_call（用于非异步上下文，通过 sync_lock 保护）

        跨上下文互斥：与 async record_call 通过 _cross_context_lock 互斥，
        避免 async 和 sync 同时持有 sqlite 连接导致死锁或数据竞争。
        """
        now = time.time()
        with self._cross_context_lock:
            with self._sync_lock:
                cursor = self._conn.execute(
                    "SELECT success_rate, avg_latency, total_calls, consecutive_failures "
                    "FROM performance WHERE model_name = ? AND task_type = ?",
                    (model, task_type),
                )
                row = cursor.fetchone()
                if row:
                    old_rate, old_latency, old_calls, old_cf = row
                    new_calls = old_calls + 1
                    if success:
                        new_successes = int(old_rate * old_calls) + 1
                        new_rate = new_successes / new_calls
                        new_latency = (old_latency * old_calls + latency) / new_calls
                        new_cf = 0
                    else:
                        new_rate = (old_rate * old_calls) / new_calls
                        new_latency = (old_latency * old_calls + latency) / new_calls
                        new_cf = old_cf + 1
                    self._conn.execute(
                        "UPDATE performance SET success_rate=?, avg_latency=?, "
                        "total_calls=?, consecutive_failures=?, last_updated=? "
                        "WHERE model_name=? AND task_type=?",
                        (new_rate, new_latency, new_calls, new_cf, now, model, task_type),
                    )
                else:
                    rate = 1.0 if success else 0.0
                    cf = 0 if success else 1
                    self._conn.execute(
                        "INSERT INTO performance "
                        "(model_name, task_type, success_rate, avg_latency, "
                        "total_calls, consecutive_failures, last_updated) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (model, task_type, rate, latency, 1, cf, now),
                    )
                self._conn.commit()

    def get_best_model(self, task_type: str, top_k: int = 3) -> List[str]:
        cursor = self._conn.execute(
            "SELECT model_name, success_rate, avg_latency, total_calls, consecutive_failures "
            "FROM performance WHERE task_type = ? "
            "ORDER BY success_rate DESC, avg_latency ASC LIMIT ?",
            (task_type, top_k),
        )
        rows = cursor.fetchall()
        result = []
        for row in rows:
            name, rate, latency, calls, cf = row
            if cf < 5:
                result.append(name)
        return result

    def get_unified_best_model(
        self,
        task_type: str,
        realtime_metrics: Dict[str, "ModelMetrics"],
        top_k: int = 3
    ) -> List[str]:
        """统一选择最佳模型：结合历史数据和实时指标"""
        historical_best = self.get_best_model(task_type, top_k * 2)

        if not historical_best:
            return list(realtime_metrics.keys())[:top_k]

        scored = []
        for model_name in set(historical_best + list(realtime_metrics.keys())):
            historical_score = 0.5
            if model_name in historical_best:
                idx = historical_best.index(model_name)
                historical_score = 1.0 - (idx * 0.2)

            realtime_score = 0.0
            if model_name in realtime_metrics:
                metrics = realtime_metrics[model_name]
                realtime_score = metrics.health_score / 100.0

            combined_score = historical_score * 0.4 + realtime_score * 0.6
            scored.append((combined_score, model_name))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [name for _, name in scored[:top_k]]

    def get_total_records(self) -> int:
        cursor = self._conn.execute("SELECT COUNT(*) FROM performance")
        return cursor.fetchone()[0]

    def close(self):
        self._conn.close()


class LearningRouter:

    EXPLORATION_RATE = 0.2
    DEGRADATION_THRESHOLD = 5

    def __init__(self, tracker: Optional[ModelPerformanceTracker] = None):
        self._tracker = tracker or ModelPerformanceTracker()
        self._degraded_models: Dict[str, Dict[str, int]] = {}

    def select_model(self, task_type: str, candidate_models: List[str]) -> str:
        if not candidate_models:
            return candidate_models[0] if candidate_models else "Qwen/Qwen3.5-4B"

        degraded = self._degraded_models.get(task_type, {})
        eligible = []
        degraded_candidates = []
        for m in candidate_models:
            if m in degraded and degraded[m] >= self.DEGRADATION_THRESHOLD:
                degraded_candidates.append(m)
            else:
                eligible.append(m)

        if not eligible:
            eligible = candidate_models
            self._degraded_models.pop(task_type, None)

        best_models = self._tracker.get_best_model(task_type, top_k=len(eligible))
        ranked = []
        for bm in best_models:
            if bm in eligible:
                ranked.append(bm)
        for m in eligible:
            if m not in ranked:
                ranked.append(m)

        if not ranked:
            return candidate_models[0]

        if len(ranked) == 1:
            return ranked[0]

        if random.random() < self.EXPLORATION_RATE:
            explorables = ranked[1:]
            if explorables:
                return random.choice(explorables)

        return ranked[0]

    def record_call(self, model: str, task_type: str, success: bool, latency: float):
        self._tracker._record_call_sync(model, task_type, success, latency)
        if not success:
            if task_type not in self._degraded_models:
                self._degraded_models[task_type] = {}
            self._degraded_models[task_type][model] = self._degraded_models[task_type].get(model, 0) + 1
        else:
            if task_type in self._degraded_models and model in self._degraded_models[task_type]:
                del self._degraded_models[task_type][model]
                if not self._degraded_models[task_type]:
                    del self._degraded_models[task_type]

    def has_sufficient_data(self) -> bool:
        return self._tracker.get_total_records() > 10


_learning_router: Optional[LearningRouter] = None
_learning_router_lock = asyncio.Lock()


async def get_learning_router() -> LearningRouter:
    global _learning_router
    if _learning_router is None:
        async with _learning_router_lock:
            if _learning_router is None:
                _learning_router = LearningRouter()
    return _learning_router


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

    # 默认降级链（硬编码兜底）
    DEFAULT_FALLBACK_ORDER = [
        "Qwen/Qwen3-8B",
        "THUDM/GLM-4-9B-0414",
        "Qwen/Qwen3.5-4B"
    ]

    def __init__(self):
        self._metrics: Dict[str, ModelMetrics] = {}
        self._lock = asyncio.Lock()
        self._fallback_order = self._load_fallback_chain("default")

    def _load_fallback_chain(self, chain_name: str = "default") -> List[str]:
        """从配置文件加载降级链"""
        config = load_agent_model_config()
        if config and "fallback_chains" in config:
            chain = config["fallback_chains"].get(chain_name, [])
            if chain:
                # 将模型 ID 转换为模型 Key
                resolved = [resolve_model_key(m) for m in chain]
                logger.info(f"已从配置加载降级链 '{chain_name}': {resolved}")
                return resolved

        logger.info(f"使用默认降级链 '{chain_name}': {self.DEFAULT_FALLBACK_ORDER}")
        return self.DEFAULT_FALLBACK_ORDER.copy()

    def reload_fallback_chain(self, chain_name: str = "default"):
        """重新加载降级链"""
        self._fallback_order = self._load_fallback_chain(chain_name)

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
        static_assignment = _LayeredModelRouterCompat.get_assignment(complexity)
        return static_assignment

    async def get_assignment_with_learning(
        self, complexity, learning_router: Optional[LearningRouter] = None
    ) -> ModelAssignment:
        static_assignment = _LayeredModelRouterCompat.get_assignment(complexity)
        if learning_router is None:
            learning_router = await get_learning_router()
        if not learning_router.has_sufficient_data():
            return static_assignment
        task_types = [
            ("architect", static_assignment.architect_model),
            ("frontend", static_assignment.frontend_model),
            ("backend", static_assignment.backend_model),
            ("reviewer", static_assignment.reviewer_model),
            ("fallback", static_assignment.fallback_model),
        ]
        all_models = [m for _, m in task_types]
        selected = {}
        for task_type, static_model in task_types:
            chosen = learning_router.select_model(task_type, all_models)
            selected[task_type] = chosen
        return ModelAssignment(
            architect_model=selected["architect"],
            frontend_model=selected["frontend"],
            backend_model=selected["backend"],
            reviewer_model=selected["reviewer"],
            fallback_model=selected["fallback"],
        )


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


@dataclass
class RoutingConfig:
    """路由配置"""
    system_overload_threshold: float = 0.8  # 系统过载阈值
    model_load_weight: float = 0.6          # 模型负载权重
    system_load_weight: float = 0.4         # 系统负载权重
    max_concurrent_requests: int = 100      # 最大并发请求数（可配置）
    enable_health_aware_routing: bool = False  # 是否启用健康感知路由（默认关闭）


# ==================== 分层模型路由（向后兼容） ====================

from app.agent.complexity import ProjectComplexity

class _LayeredModelRouterCompat:
    """分层模型路由器 - 根据复杂度分配最优模型组合（向后兼容）"""

    # 默认分配（硬编码兜底）
    DEFAULT_ASSIGNMENTS = {
        ProjectComplexity.SIMPLE: ModelAssignment(
            architect_model="Qwen/Qwen3.5-4B",
            frontend_model="Qwen/Qwen3-8B",
            backend_model="Qwen/Qwen3-8B",
            reviewer_model="Qwen/Qwen3-8B",
            fallback_model="Qwen/Qwen3.5-4B"
        ),
        ProjectComplexity.SMALL: ModelAssignment(
            architect_model="THUDM/GLM-Z1-9B-0414",
            frontend_model="Qwen/Qwen3-8B",
            backend_model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            reviewer_model="THUDM/GLM-Z1-9B-0414",
            fallback_model="Qwen/Qwen3-8B"
        ),
        ProjectComplexity.MEDIUM: ModelAssignment(
            architect_model="THUDM/GLM-Z1-9B-0414",
            frontend_model="Qwen/Qwen3-8B",
            backend_model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            reviewer_model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            fallback_model="Qwen/Qwen3-8B"
        ),
        ProjectComplexity.LARGE: ModelAssignment(
            architect_model="THUDM/GLM-Z1-9B-0414",
            frontend_model="Qwen/Qwen3-8B",
            backend_model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            reviewer_model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            fallback_model="Qwen/Qwen3-8B"
        ),
        # ENTERPRISE 与 LARGE 共享相同分配（模型能力无差异）
        ProjectComplexity.ENTERPRISE: None,

    }

    # 运行时缓存的分配（从配置文件加载）
    _cached_assignments: Optional[Dict[ProjectComplexity, ModelAssignment]] = None
    _config_loaded: bool = False

    @classmethod
    def _load_config_assignments(cls) -> Dict[ProjectComplexity, ModelAssignment]:
        """从配置文件加载模型分配"""
        if cls._config_loaded:
            return cls._cached_assignments or cls.DEFAULT_ASSIGNMENTS

        config = load_agent_model_config()
        if not config or "assignments" not in config:
            cls._config_loaded = True
            cls._cached_assignments = None
            return cls.DEFAULT_ASSIGNMENTS

        assignments = {}
        for complexity_name, model_ids in config["assignments"].items():
            try:
                complexity = ProjectComplexity[complexity_name]
                # 将模型 ID 转换为模型 Key
                assignments[complexity] = ModelAssignment(
                    architect_model=resolve_model_key(model_ids.get("architect_model", "")),
                    frontend_model=resolve_model_key(model_ids.get("frontend_model", "")),
                    backend_model=resolve_model_key(model_ids.get("backend_model", "")),
                    reviewer_model=resolve_model_key(model_ids.get("reviewer_model", "")),
                    fallback_model=resolve_model_key(model_ids.get("fallback_model", "")),
                )
            except (KeyError, ValueError) as e:
                logger.warning(f"解析配置文件中的复杂度 '{complexity_name}' 失败: {e}")
                continue

        if assignments:
            # ENTERPRISE 与 LARGE 共享分配（模型能力无差异）
            if ProjectComplexity.ENTERPRISE not in assignments and ProjectComplexity.LARGE in assignments:
                assignments[ProjectComplexity.ENTERPRISE] = assignments[ProjectComplexity.LARGE]
            cls._cached_assignments = assignments
            cls._config_loaded = True
            logger.info(f"已从配置文件加载 {len(assignments)} 个模型分配")
            return assignments

        cls._config_loaded = True
        cls._cached_assignments = None
        return cls.DEFAULT_ASSIGNMENTS

    @classmethod
    def reload_config(cls):
        """重新加载配置文件（用于动态更新）"""
        cls._config_loaded = False
        cls._cached_assignments = None
        return cls._load_config_assignments()

    @classmethod
    def get_assignment(cls, complexity: ProjectComplexity) -> ModelAssignment:
        assignments = cls._load_config_assignments()
        result = assignments.get(complexity)
        if result is None:
            # ENTERPRISE 降级到 LARGE（模型分配无差异）
            if complexity == ProjectComplexity.ENTERPRISE:
                result = assignments.get(ProjectComplexity.LARGE)
        if result is None:
            result = assignments.get(complexity, cls.DEFAULT_ASSIGNMENTS[ProjectComplexity.MEDIUM])
        return result

    @classmethod
    async def get_best_model_with_health_awareness(
        cls,
        candidate_models: List[str],
        task_type: str = "general",
        routing_config: Optional[RoutingConfig] = None
    ) -> str:
        """
        带健康感知的模型选择

        NOTE: Currently unused (enable_health_awareness defaults to False).
        Callers should set RoutingConfig(enable_health_awareness=True) to activate.
        """
        if not candidate_models:
            return "Qwen/Qwen3.5-4B"

        config = routing_config or RoutingConfig()

        # 如果未启用健康感知路由，使用传统方式
        if not config.enable_health_aware_routing:
            router = await get_dynamic_router()
            return await router.get_best_model(candidate_models, task_type)

        # 获取系统负载快照
        snapshot = await system_load_monitor.get_load_snapshot()

        # 检查系统是否过载
        if system_load_monitor.is_system_overloaded(config.system_overload_threshold):
            logger.warning(f"系统过载，启用降级策略: {snapshot}")
            # 选择负载最轻的模型
            best_model = min(
                candidate_models,
                key=lambda m: system_load_monitor.get_model_load_score(m)
            )
            logger.info(f"健康感知路由: 选择降级模型 {best_model} (系统过载)")
            return best_model

        # 正常情况：结合模型健康和系统负载评分
        router = await get_dynamic_router()
        healthy_models = []

        for model_name in candidate_models:
            metrics = router.get_or_create_metrics(model_name)
            if metrics.consecutive_failures < 3:  # 未熔断
                healthy_models.append(model_name)

        if not healthy_models:
            return "Qwen/Qwen3.5-4B"

        # 计算综合评分
        def calculate_comprehensive_score(model_name: str) -> float:
            # 模型健康评分 (0-100)
            metrics = router.get_or_create_metrics(model_name)
            model_health_score = metrics.health_score / 100.0

            # 系统负载评分 (0-1, 越低越好)
            system_load_score = system_load_monitor.get_model_load_score(model_name)

            # 综合评分 = 模型健康 * 权重 + (1 - 系统负载) * 权重
            comprehensive_score = (
                model_health_score * config.model_load_weight +
                (1.0 - system_load_score) * config.system_load_weight
            )

            return comprehensive_score

        best_model = max(healthy_models, key=calculate_comprehensive_score)
        logger.info(f"健康感知路由 [{task_type}]: {best_model}")
        return best_model


# ==================== get_model_config 工具函数 ====================

# SiliconFlow 模型上下文窗口映射（来源：模型广场页面手动维护）
# 当 API 支持返回 context_length 后可自动同步，当前为静态映射
# 特殊模型（语音/图像/视频）无传统上下文概念，不在此映射中
MODEL_CONTEXT_LENGTHS: Dict[str, int] = {
    # Qwen 系列
    "Qwen/Qwen3.5-4B": 256 * 1024,       # 256k
    "Qwen/Qwen3-8B": 128 * 1024,         # 128k
    "Qwen/Qwen2.5-7B-Instruct": 32 * 1024,  # 32k
    "Qwen/Qwen2.5-Coder-32B-Instruct": 32 * 1024,
    "Qwen/Qwen2.5-72B-Instruct": 32 * 1024,
    "Qwen/QVQ-72B-Preview": 32 * 1024,
    # DeepSeek 系列
    "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B": 128 * 1024,  # 128k
    "deepseek-ai/DeepSeek-OCR": 8 * 1024,                  # 8k
    "deepseek-ai/DeepSeek-R1": 64 * 1024,
    "deepseek-ai/DeepSeek-V3": 64 * 1024,
    "deepseek-ai/DeepSeek-V2.5": 32 * 1024,
    # GLM 系列
    "THUDM/GLM-Z1-9B-0414": 128 * 1024,   # 128k
    "THUDM/GLM-4-9B-0414": 32 * 1024,     # 32k
    "THUDM/GLM-4.1V-9B-Thinking": 32 * 1024,
    # Embedding / Reranker（无传统上下文，按最大输入估算）
    "BAAI/bge-m3": 8 * 1024,                          # 8k
    "BAAI/bge-reranker-v2-m3": 8 * 1024,              # 8k
    "BAAI/bge-large-zh-v1.5": 512,                    # 0.5k
    "netease-youdao/bce-embedding-base_v1": 512,      # 0.5k
    "netease-youdao/bce-reranker-base_v1": 512,       # 0.5k
    # 翻译模型
    "tencent/Hunyuan-MT-7B": 32 * 1024,   # 32k
    # 特殊模型（语音/图像/视频）不在此映射中，使用默认值
    # Kwai-Kolors/Kolors          - 文生图，无上下文概念
    # FunAudioLLM/SenseVoiceSmall  - 语音识别
    # TeleAI/TeleSpeechASR         - 语音识别
}

# 安全默认值
_DEFAULT_CONTEXT_LENGTH = 32768
_DEFAULT_MAX_OUTPUT = 4096
_RESERVE_INPUT_RATIO = 0.25  # 输入预留 25% 上下文


def get_context_length(model_name: str, api_key_token: str = None) -> int:
    """获取模型上下文窗口长度（token）

    优先级：
    1. 用户自定义配置（如果提供了 api_key_token）
    2. 配置文件 model_context_lengths（管理员全局配置）
    3. 代码内置 MODEL_CONTEXT_LENGTHS
    4. 动态供应商
    5. 自定义供应商（用户自接入 API Key）
    6. 默认值 32768

    Args:
        model_name: 模型名称
        api_key_token: API Key Token（可选），如果提供则优先查该 Token 的自定义配置
    """
    # 用户自定义配置（通过 api_key_token 查找）
    if api_key_token:
        try:
            from app.services.apikey_manager import get_apikey_manager
            apikey_manager = get_apikey_manager()
            context_lengths = apikey_manager.get_context_lengths_by_token(api_key_token)
            if context_lengths and model_name in context_lengths:
                val = context_lengths[model_name]
                if val and val > 0:
                    return int(val)
        except Exception as e:
            logger.debug(f"模型路由操作失败：{e}")

    # 配置文件（管理员全局配置）
    config = load_agent_model_config()
    if config and "model_context_lengths" in config:
        val = config["model_context_lengths"].get(model_name)
        if val and val > 0:
            return int(val)
    # 代码内置映射
    if model_name in MODEL_CONTEXT_LENGTHS:
        return MODEL_CONTEXT_LENGTHS[model_name]
    # 动态供应商
    try:
        from app.utils.aicloud.dynamic_provider import get_dynamic_provider_manager
        manager = get_dynamic_provider_manager()
        dp = manager.get_by_model(model_name)
        if dp:
            for m in dp.models:
                if m.id == model_name and m.context_length > 0:
                    return m.context_length
    except Exception as e:
        logger.debug(f"模型路由操作失败：{e}")
    # 自定义供应商（用户自接入 API Key）
    try:
        from app.services.custom_provider_manager import get_custom_provider_manager
        cp_manager = get_custom_provider_manager()
        for provider in cp_manager.providers.values():
            if not provider.enabled:
                continue
            for m in provider.models:
                if m.id == model_name and m.context_length > 0:
                    return m.context_length
    except Exception as e:
        logger.debug(f"模型路由操作失败：{e}")
    return _DEFAULT_CONTEXT_LENGTH


def get_max_output_tokens(model_name: str, reserve_for_input: int = 0, api_key_token: str = None) -> int:
    """计算模型最大输出 token 数

    Args:
        model_name: 模型名称
        reserve_for_input: 预留给输入的 token 数，0 则按比例自动计算
        api_key_token: API Key Token（可选）

    Returns:
        建议的最大输出 token 数
    """
    ctx = get_context_length(model_name, api_key_token)
    if reserve_for_input > 0:
        max_out = ctx - reserve_for_input
    else:
        max_out = int(ctx * (1 - _RESERVE_INPUT_RATIO))
    # 不超过模型能力，不低于最小值
    return max(1024, min(max_out, ctx))


def get_model_config(model_name: str, task_type: str = "generate", api_key_token: str = None) -> Dict[str, Any]:
    """获取模型的最佳配置参数（自动适配上下文窗口）

    Args:
        model_name: 模型名称
        task_type: 任务类型
        api_key_token: API Key Token（可选）
    """
    ctx_len = get_context_length(model_name, api_key_token)
    max_out = get_max_output_tokens(model_name, api_key_token=api_key_token)

    # 动态计算 max_tokens：按上下文窗口大小分级
    # - 小上下文 (<=32K)：取 max_out 的 25%，下限 4096，上限 8192
    # - 中上下文 (32K-64K)：取 max_out 的 20%，下限 6144，上限 12288
    # - 大上下文 (>64K)：取 max_out 的 15%，下限 8192，上限 16384
    if ctx_len <= 32768:
        dynamic_max_tokens = max(4096, min(8192, int(max_out * 0.25)))
    elif ctx_len <= 65536:
        dynamic_max_tokens = max(6144, min(12288, int(max_out * 0.20)))
    else:
        dynamic_max_tokens = max(8192, min(16384, int(max_out * 0.15)))

    # 动态计算 thinking_budget：取 max_tokens 的 50%，下限 2048，上限 4096
    dynamic_thinking_budget = max(2048, min(4096, dynamic_max_tokens // 2))

    configs = {
        "THUDM/GLM-Z1-9B-0414": {"temperature": 0.6, "max_tokens": dynamic_max_tokens, "thinking_budget": dynamic_thinking_budget, "context_length": ctx_len, "timeout": 180},
        "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B": {"temperature": 0.6, "max_tokens": dynamic_max_tokens, "thinking_budget": dynamic_thinking_budget, "context_length": ctx_len, "timeout": 180},
        "Qwen/Qwen3.5-4B": {"temperature": 0.7, "max_tokens": dynamic_max_tokens, "thinking_budget": dynamic_thinking_budget, "context_length": ctx_len, "timeout": 120},
        "Qwen/Qwen3-8B": {"temperature": 0.7, "max_tokens": dynamic_max_tokens, "thinking_budget": dynamic_thinking_budget, "context_length": ctx_len, "timeout": 180},
        "Qwen/Qwen2.5-7B-Instruct": {"temperature": 0.7, "max_tokens": dynamic_max_tokens, "thinking_budget": dynamic_thinking_budget, "context_length": ctx_len, "timeout": 180},
        "THUDM/GLM-4-9B-0414": {"temperature": 0.7, "max_tokens": dynamic_max_tokens, "thinking_budget": dynamic_thinking_budget, "context_length": ctx_len, "timeout": 180},
    }
    return configs.get(model_name, {
        "temperature": 0.7,
        "max_tokens": max_out,
        "thinking_budget": min(2048, max_out // 2),
        "context_length": ctx_len,
        "timeout": 300,
    })


# 为 DynamicModelRouter 添加 get_model_config 类方法（向后兼容）
DynamicModelRouter.get_model_config = staticmethod(get_model_config)
DynamicModelRouter.get_context_length = staticmethod(get_context_length)
DynamicModelRouter.get_max_output_tokens = staticmethod(get_max_output_tokens)
LayeredModelRouter.get_model_config = staticmethod(get_model_config)
LayeredModelRouter.get_context_length = staticmethod(get_context_length)
LayeredModelRouter.get_max_output_tokens = staticmethod(get_max_output_tokens)
