"""动态模型路由器 - 基于延迟、成功率、队列深度的智能路由（支持全局健康感知）"""

import asyncio
import os
import random
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import deque
import logging
from pathlib import Path

from app.utils.system_load import system_load_monitor
from app.utils.model_config_io import load_model_config, save_model_config

logger = logging.getLogger(__name__)

# Agent 运行时配置文件路径；该文件由 ModelConfigManager 从管理面配置派生生成。
AGENT_MODEL_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../../data/agent_model_config.yaml")

# 备选模型 ID → Key 映射（配置文件不可用时的兜底）
_FALLBACK_MODEL_ID_TO_KEY: Dict[str, str] = {
    "deepseek-r1": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
    "qwen3-8b": "Qwen/Qwen3-8B",
    "glm-z1-9b": "THUDM/GLM-Z1-9B-0414",
    "glm-4-9b": "THUDM/GLM-4-9B-0414",
}


_provider_map_cache: Optional[Dict[str, Any]] = None
_model_id_key_cache: Optional[Dict[str, str]] = None


def _build_provider_map() -> Dict[str, "ModelProvider"]:
    """从 Agent 运行时配置构建 model_name -> provider 映射。"""
    global _provider_map_cache
    from app.utils.aicloud.provider_router import ModelProvider
    try:
        config = load_model_config(Path(AGENT_MODEL_CONFIG_PATH))
        models = config.get("models", {})
        provider_map = {}
        provider_enum_map = {
            "siliconflow": ModelProvider.SILICONFLOW,
            "dashscope": ModelProvider.DASHSCOPE,
            "zhipu": ModelProvider.ZHIPU,
            "deepseek": ModelProvider.DEEPSEEK,
        }
        for model_id, m in models.items():
            name = m.get("name", "")
            provider_str = m.get("provider", "siliconflow")
            provider = provider_enum_map.get(provider_str, ModelProvider.SILICONFLOW)
            if name:
                provider_map[name] = provider
        _provider_map_cache = provider_map
        return provider_map
    except Exception:
        return _provider_map_cache or {}


def _build_model_id_to_key() -> Dict[str, str]:
    """从 Agent 运行时配置构建 model_id -> model_key 映射。"""
    global _model_id_key_cache
    try:
        config = load_model_config(Path(AGENT_MODEL_CONFIG_PATH))
        models = config.get("models", {})
        mapping = {}
        for model_id, m in models.items():
            name = m.get("name", "")
            if name:
                mapping[model_id] = name
        _model_id_key_cache = mapping
        return mapping
    except Exception:
        return _model_id_key_cache or _FALLBACK_MODEL_ID_TO_KEY


def get_model_id_to_key() -> Dict[str, str]:
    """获取模型ID到模型Key的映射（支持缓存刷新）"""
    global _model_id_key_cache
    if _model_id_key_cache is None:
        _build_model_id_to_key()
    return _model_id_key_cache or _FALLBACK_MODEL_ID_TO_KEY


def get_model_provider_map() -> Dict[str, Any]:
    """获取模型名到Provider的映射（支持缓存刷新）"""
    global _provider_map_cache
    if _provider_map_cache is None:
        _build_provider_map()
    return _provider_map_cache or {}


def invalidate_model_mapping_cache():
    """刷新模型映射缓存（调用后重建 MODEL_ID_TO_KEY / MODEL_PROVIDER_MAP）"""
    global MODEL_ID_TO_KEY, MODEL_PROVIDER_MAP, MODEL_KEY_TO_ID, _model_id_key_cache, _provider_map_cache
    _model_id_key_cache = None
    _provider_map_cache = None
    MODEL_ID_TO_KEY = _build_model_id_to_key()
    MODEL_PROVIDER_MAP = _build_provider_map()
    MODEL_KEY_TO_ID = {v: k for k, v in MODEL_ID_TO_KEY.items()}


# 模型 ID 到模型 Key 的映射（从运行时 YAML 配置动态生成）
MODEL_ID_TO_KEY = _build_model_id_to_key()

# 模型 Key 到模型 ID 的反向映射
MODEL_KEY_TO_ID = {v: k for k, v in MODEL_ID_TO_KEY.items()}

# 模型名称到供应商的映射（从运行时 YAML 配置动态生成）
MODEL_PROVIDER_MAP = _build_provider_map()


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
            config = load_model_config(Path(AGENT_MODEL_CONFIG_PATH))
            logger.info(f"已加载 Agent 模型配置: {AGENT_MODEL_CONFIG_PATH}")
            return config
    except Exception as e:
        logger.warning(f"加载 Agent 模型配置失败: {e}")
    return None


def save_agent_model_config(config: Dict[str, Any]) -> bool:
    """保存 Agent 模型配置到文件"""
    try:
        os.makedirs(os.path.dirname(AGENT_MODEL_CONFIG_PATH), exist_ok=True)
        save_model_config(Path(AGENT_MODEL_CONFIG_PATH), config)
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
            return candidate_models[0] if candidate_models else "Qwen/Qwen3-8B"

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
        "Qwen/Qwen3-8B"
    ]

    def __init__(self):
        self._metrics: Dict[str, ModelMetrics] = {}
        self._lock = asyncio.Lock()
        self._fallback_order = self._load_fallback_chain("default")

    def _load_fallback_chain(self, chain_name: str = "default") -> List[str]:
        """从配置文件加载降级链（v3.0: 统一为 fallback_chain）"""
        config = load_agent_model_config()
        if config:
            # v3.0 格式：直接用 fallback_chain
            if "fallback_chain" in config:
                chain = config["fallback_chain"]
                if chain:
                    resolved = [resolve_model_key(m) for m in chain]
                    logger.info(f"已从配置加载降级链: {resolved}")
                    return resolved
            # v2.0 兼容：fallback_chains.default
            if "fallback_chains" in config:
                chain = config["fallback_chains"].get(chain_name, [])
                if chain:
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
                # 所有模型都熔断，尝试降级链中第一个健康的模型
                for fallback in self._fallback_order:
                    fb_metrics = self.get_or_create_metrics(fallback)
                    if fb_metrics.consecutive_failures < 3:
                        logger.warning(f"所有候选模型熔断，使用降级模型: {fallback}")
                        return fallback
                # 降级链也全部熔断，返回第一个降级模型（强制重试）
                logger.error(f"所有候选和降级模型都已熔断，强制使用: {self._fallback_order[0]}")
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

    def get_assignment(self, complexity=None) -> ModelAssignment:
        """获取模型分配（不再依赖复杂度，直接读取 roles 配置）"""
        static_assignment = _load_roles_assignment()
        return self._apply_circuit_breaker(static_assignment)

    def _apply_circuit_breaker(self, assignment: "ModelAssignment") -> "ModelAssignment":
        """熔断降级：连续失败 ≥ 2 次的模型自动用 fallback_model 替代"""
        fallback = assignment.fallback_model
        circuit_broken = []
        for field in ("architect_model", "frontend_model", "backend_model", "reviewer_model"):
            model = getattr(assignment, field)
            metrics = self.get_or_create_metrics(model)
            if metrics.consecutive_failures >= 2 and model != fallback:
                setattr(assignment, field, fallback)
                circuit_broken.append(f"{field}: {model} -> {fallback}")
        if circuit_broken:
            logger.warning(f"熔断降级触发: {circuit_broken}")
        return assignment

    async def get_assignment_with_learning(
        self, complexity=None, learning_router: Optional[LearningRouter] = None
    ) -> ModelAssignment:
        """获取模型分配（带学习路由，不再依赖复杂度）"""
        static_assignment = _load_roles_assignment()
        if learning_router is None:
            learning_router = await get_learning_router()
        if not learning_router.has_sufficient_data():
            return self._apply_circuit_breaker(static_assignment)
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
        result = ModelAssignment(
            architect_model=selected["architect"],
            frontend_model=selected["frontend"],
            backend_model=selected["backend"],
            reviewer_model=selected["reviewer"],
            fallback_model=selected["fallback"],
        )
        return self._apply_circuit_breaker(result)


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


class _LayeredModelRouterCompat:
    """兼容旧版按项目复杂度读取角色模型分配的接口。"""

    _config_loaded = False
    _cached_assignments: Optional[Dict[str, ModelAssignment]] = None

    @classmethod
    def get_assignment(cls, complexity) -> ModelAssignment:
        from app.agent.complexity import ProjectComplexity

        if not cls._config_loaded:
            config = load_agent_model_config() or {}
            assignments = config.get("assignments", {})
            defaults = ModelAssignment(
                architect_model="Qwen/Qwen3-8B",
                frontend_model="Qwen/Qwen3-8B",
                backend_model="Qwen/Qwen3-8B",
                reviewer_model="Qwen/Qwen3-8B",
                fallback_model="Qwen/Qwen3-8B",
            )
            parsed: Dict[str, ModelAssignment] = {}
            for level in ProjectComplexity:
                raw = assignments.get(level.name, assignments.get(level.value, {}))
                parsed[level.value] = ModelAssignment(
                    **{field_name: resolve_model_key(raw.get(field_name, getattr(defaults, field_name)))
                       for field_name in (
                           "architect_model", "frontend_model", "backend_model",
                           "reviewer_model", "fallback_model",
                       )}
                )
            cls._cached_assignments = parsed
            cls._config_loaded = True

        level = getattr(complexity, "value", str(complexity)).lower()
        if level == ProjectComplexity.ENTERPRISE.value:
            level = ProjectComplexity.LARGE.value
        return cls._cached_assignments[level]

    @classmethod
    def reload_config(cls):
        cls._config_loaded = False
        cls._cached_assignments = None


@dataclass
class RoutingConfig:
    """路由配置"""
    system_overload_threshold: float = 0.8  # 系统过载阈值
    model_load_weight: float = 0.6          # 模型负载权重
    system_load_weight: float = 0.4         # 系统负载权重
    max_concurrent_requests: int = 100      # 最大并发请求数（可配置）
    enable_health_aware_routing: bool = False  # 是否启用健康感知路由（默认关闭）


# ==================== 角色模型分配（五角色配置） ====================

# 默认角色分配（硬编码兜底）
_DEFAULT_ROLES = {
    "architect": "THUDM/GLM-Z1-9B-0414",
    "frontend": "Qwen/Qwen3-8B",
    "backend": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
    "reviewer": "THUDM/GLM-4-9B-0414",
    "fallback": "Qwen/Qwen3-8B",
}

_roles_cache: Optional[Dict[str, str]] = None


def _load_roles_assignment() -> ModelAssignment:
    """从配置文件加载角色模型分配（v3.0 简化格式）"""
    global _roles_cache
    if _roles_cache is not None:
        return ModelAssignment(
            architect_model=_roles_cache["architect"],
            frontend_model=_roles_cache["frontend"],
            backend_model=_roles_cache["backend"],
            reviewer_model=_roles_cache["reviewer"],
            fallback_model=_roles_cache["fallback"],
        )

    config = load_agent_model_config()
    if config and "roles" in config:
        raw = config["roles"]
        roles = {}
        for role, model_id in raw.items():
            roles[role] = resolve_model_key(model_id)
        # 用默认值补全缺失字段
        for key, default_val in _DEFAULT_ROLES.items():
            if key not in roles:
                roles[key] = default_val
        _roles_cache = roles
        logger.info(f"已从配置加载角色模型分配: {roles}")
        return ModelAssignment(
            architect_model=roles["architect"],
            frontend_model=roles["frontend"],
            backend_model=roles["backend"],
            reviewer_model=roles["reviewer"],
            fallback_model=roles["fallback"],
        )

    # 配置文件不存在或格式不对，使用硬编码默认值
    _roles_cache = _DEFAULT_ROLES.copy()
    return ModelAssignment(**{k + "_model": v for k, v in _DEFAULT_ROLES.items()})


def reload_roles_config():
    """重新加载角色配置"""
    global _roles_cache
    _roles_cache = None
    invalidate_model_mapping_cache()
    return _load_roles_assignment()


async def get_best_model_with_health_awareness(
    candidate_models: List[str],
    task_type: str = "general",
    routing_config: Optional[RoutingConfig] = None
) -> str:
    """
    带健康感知的模型选择

    Callers should set RoutingConfig(enable_health_awareness=True) to activate.
    """
    if not candidate_models:
        return "Qwen/Qwen3-8B"

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
        return "Qwen/Qwen3-8B"

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

    # 动态计算 thinking_budget：从配置读取 thinking_ratio，支持按模型覆盖
    config = load_agent_model_config()
    models_config = config.get("models", {}) if config else {}
    global_ratio = config.get("global_thinking_ratio", 0.5) if config else 0.5

    # 解析模型 ID 到 Key，用于查找配置
    model_key = resolve_model_key(model_name)
    model_id = MODEL_KEY_TO_ID.get(model_key, model_name)

    # 优先用模型配置中的 thinking_ratio，否则用全局默认值
    model_cfg = models_config.get(model_id, {})
    thinking_ratio = model_cfg.get("thinking_ratio", global_ratio)

    # thinking_ratio=0 表示禁用思考，否则按比例计算
    if thinking_ratio > 0:
        dynamic_thinking_budget = max(2048, int(dynamic_max_tokens * thinking_ratio))
    else:
        dynamic_thinking_budget = 0

    # 从统一配置读取模型参数，不再硬编码
    model_cfg = models_config.get(model_id, {})
    if not model_cfg:
        model_cfg = models_config.get(model_key, {})

    return {
        "temperature": model_cfg.get("temperature", 0.7),
        "max_tokens": model_cfg.get("max_tokens", dynamic_max_tokens),
        "thinking_budget": model_cfg.get("thinking_budget", dynamic_thinking_budget),
        "context_length": ctx_len,
        "timeout": model_cfg.get("timeout", 300),
    }


# 为 DynamicModelRouter 添加 get_model_config 类方法（向后兼容）
DynamicModelRouter.get_model_config = staticmethod(get_model_config)
DynamicModelRouter.get_context_length = staticmethod(get_context_length)
DynamicModelRouter.get_max_output_tokens = staticmethod(get_max_output_tokens)
LayeredModelRouter.get_model_config = staticmethod(get_model_config)
LayeredModelRouter.get_context_length = staticmethod(get_context_length)
LayeredModelRouter.get_max_output_tokens = staticmethod(get_max_output_tokens)
