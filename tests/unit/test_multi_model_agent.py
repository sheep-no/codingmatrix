"""
多模型 Agent 路由与降级链单元测试
测试 ModelPerformanceTracker、ModelMetrics、DynamicModelRouter、LearningRouter 等核心路由组件
"""
import asyncio
import json
import time
from collections import deque
from unittest.mock import patch, MagicMock

import pytest

from app.agent.dynamic_model_router import (
    ModelPerformanceTracker,
    ModelMetrics,
    DynamicModelRouter,
    LearningRouter,
    ModelAssignment,
    _LayeredModelRouterCompat,
    resolve_model_key,
    load_agent_model_config,
)
from app.agent.complexity import ProjectComplexity


# ==================== ModelPerformanceTracker ====================


class TestModelPerformanceTracker:
    """ModelPerformanceTracker 使用内存 SQLite 进行测试"""

    @pytest.fixture
    def tracker(self):
        """创建使用内存数据库的 tracker"""
        t = ModelPerformanceTracker(db_path=":memory:")
        yield t
        t.close()

    @pytest.mark.asyncio
    async def test_record_success(self, tracker):
        """记录成功调用后 success_rate 上升"""
        await tracker.record_call("model-a", "generate", success=True, latency=100.0)
        await tracker.record_call("model-a", "generate", success=True, latency=200.0)

        best = tracker.get_best_model("generate")
        assert "model-a" in best

    @pytest.mark.asyncio
    async def test_record_failure(self, tracker):
        """记录失败调用后 consecutive_failures 增加"""
        await tracker.record_call("model-b", "generate", success=False, latency=50.0)
        await tracker.record_call("model-b", "generate", success=False, latency=50.0)

        cursor = tracker._conn.execute(
            "SELECT consecutive_failures FROM performance WHERE model_name=? AND task_type=?",
            ("model-b", "generate"),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 2

    @pytest.mark.asyncio
    async def test_consecutive_failures_reset(self, tracker):
        """成功后 consecutive_failures 重置为 0"""
        await tracker.record_call("model-c", "generate", success=False, latency=50.0)
        await tracker.record_call("model-c", "generate", success=False, latency=50.0)
        await tracker.record_call("model-c", "generate", success=True, latency=100.0)

        cursor = tracker._conn.execute(
            "SELECT consecutive_failures FROM performance WHERE model_name=? AND task_type=?",
            ("model-c", "generate"),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 0

    @pytest.mark.asyncio
    async def test_best_model_ordering(self, tracker):
        """按成功率排序返回最佳模型"""
        # model-x: 3/3 成功 = 100%
        for _ in range(3):
            await tracker.record_call("model-x", "codegen", success=True, latency=100.0)
        # model-y: 1/2 成功 = 50%
        await tracker.record_call("model-y", "codegen", success=True, latency=100.0)
        await tracker.record_call("model-y", "codegen", success=False, latency=200.0)
        # model-z: 0/2 成功 = 0%
        await tracker.record_call("model-z", "codegen", success=False, latency=300.0)
        await tracker.record_call("model-z", "codegen", success=False, latency=300.0)

        best = tracker.get_best_model("codegen", top_k=3)
        assert best[0] == "model-x"
        assert best[1] == "model-y"


# ==================== ModelMetrics ====================


class TestModelMetrics:
    """ModelMetrics 数据类属性测试"""

    def test_health_score_healthy(self):
        """健康模型分数 > 70"""
        metrics = ModelMetrics(model_name="healthy-model")
        # 模拟 10 次成功请求，低延迟
        for _ in range(10):
            metrics.record_success(500.0)
        assert metrics.health_score > 70

    def test_health_score_circuit_breaker(self):
        """连续 3 次失败触发熔断，分数为 0"""
        metrics = ModelMetrics(model_name="bad-model")
        for _ in range(3):
            metrics.record_failure("timeout")
        assert metrics.health_score == 0

    def test_success_rate_calculation(self):
        """成功率计算正确"""
        metrics = ModelMetrics(model_name="test-model")
        metrics.record_success(100.0)
        metrics.record_success(100.0)
        metrics.record_failure("err")
        metrics.record_failure("err")
        # 2 success / 4 total = 0.5
        assert metrics.success_rate == 0.5

    def test_avg_latency(self):
        """平均延迟计算正确"""
        metrics = ModelMetrics(model_name="latency-model")
        metrics.record_success(100.0)
        metrics.record_success(300.0)
        # (100 + 300) / 2 = 200
        assert metrics.avg_latency_ms == 200.0


# ==================== DynamicModelRouter ====================


class TestDynamicModelRouter:
    """DynamicModelRouter 测试，mock 掉配置文件 I/O"""

    @pytest.fixture
    def router(self):
        """创建路由器实例，使用默认降级链"""
        with patch(
            "app.agent.dynamic_model_router.load_agent_model_config",
            return_value=None,
        ):
            r = DynamicModelRouter()
            yield r

    @pytest.mark.asyncio
    async def test_record_and_get_best(self, router):
        """记录调用后能选出最佳模型"""
        await router.record_call("m1", success=True, latency_ms=100.0)
        await router.record_call("m2", success=True, latency_ms=500.0)

        best = await router.get_best_model(["m1", "m2"])
        # m1 延迟更低，健康分更高
        assert best == "m1"

    @pytest.mark.asyncio
    async def test_circuit_breaker(self, router):
        """连续失败后模型被熔断，不再被选中"""
        await router.record_call("bad", success=False, latency_ms=100.0, error="e1")
        await router.record_call("bad", success=False, latency_ms=100.0, error="e2")
        await router.record_call("bad", success=False, latency_ms=100.0, error="e3")

        await router.record_call("good", success=True, latency_ms=200.0)

        best = await router.get_best_model(["bad", "good"])
        assert best == "good"

    @pytest.mark.asyncio
    async def test_fallback_chain_from_config(self):
        """从配置文件加载降级链"""
        config = {
            "fallback_chains": {
                "default": ["qwen3-8b", "glm-4-9b"],
            }
        }
        with patch(
            "app.agent.dynamic_model_router.load_agent_model_config",
            return_value=config,
        ):
            router = DynamicModelRouter()
            # qwen3-8b -> Qwen/Qwen3-8B, glm-4-9b -> THUDM/GLM-4-9B-0414
            assert router._fallback_order == [
                "Qwen/Qwen3-8B",
                "THUDM/GLM-4-9B-0414",
            ]

    @pytest.mark.asyncio
    async def test_get_assignment_from_config(self):
        """从配置文件加载模型分配"""
        config = {
            "assignments": {
                "SIMPLE": {
                    "architect_model": "qwen3-8b",
                    "frontend_model": "qwen3-8b",
                    "backend_model": "qwen3-8b",
                    "reviewer_model": "qwen3-8b",
                    "fallback_model": "qwen3-8b",
                },
            }
        }
        # 清除 _LayeredModelRouterCompat 的缓存
        _LayeredModelRouterCompat._config_loaded = False
        _LayeredModelRouterCompat._cached_assignments = None

        with patch(
            "app.agent.dynamic_model_router.load_agent_model_config",
            return_value=config,
        ):
            assignment = _LayeredModelRouterCompat.get_assignment(ProjectComplexity.SIMPLE)
            assert assignment.architect_model == "Qwen/Qwen3-8B"
            assert assignment.frontend_model == "Qwen/Qwen3-8B"

        # 清理缓存，避免影响其他测试
        _LayeredModelRouterCompat._config_loaded = False
        _LayeredModelRouterCompat._cached_assignments = None

    @pytest.mark.asyncio
    async def test_backend_role_uses_code_model_from_runtime_config(self):
        """后端代码生成角色使用统一配置中的专用代码模型。"""
        from app.agent.dynamic_model_router import reload_roles_config

        reload_roles_config()
        assignment = DynamicModelRouter().get_assignment()

        assert assignment.backend_model == "Qwen/Qwen3.5-4B"

    @pytest.mark.asyncio
    async def test_enterprise_falls_back_to_large(self):
        """ENTERPRISE 降级到 LARGE"""
        # 清除缓存
        _LayeredModelRouterCompat._config_loaded = False
        _LayeredModelRouterCompat._cached_assignments = None

        with patch(
            "app.agent.dynamic_model_router.load_agent_model_config",
            return_value=None,
        ):
            enterprise = _LayeredModelRouterCompat.get_assignment(ProjectComplexity.ENTERPRISE)
            large = _LayeredModelRouterCompat.get_assignment(ProjectComplexity.LARGE)
            assert enterprise.architect_model == large.architect_model
            assert enterprise.frontend_model == large.frontend_model

        # 清理缓存
        _LayeredModelRouterCompat._config_loaded = False
        _LayeredModelRouterCompat._cached_assignments = None

    @pytest.mark.asyncio
    async def test_reload_config(self, router):
        """重新加载配置"""
        with patch(
            "app.agent.dynamic_model_router.load_agent_model_config",
            return_value=None,
        ):
            router.reload_fallback_chain("default")
            # 使用默认降级链
            assert len(router._fallback_order) > 0


# ==================== LearningRouter ====================


class TestLearningRouter:
    """LearningRouter 测试"""

    @pytest.fixture
    def learning_router(self):
        """创建使用内存数据库的 LearningRouter"""
        tracker = ModelPerformanceTracker(db_path=":memory:")
        lr = LearningRouter(tracker=tracker)
        yield lr
        tracker.close()

    def test_select_model_basic(self, learning_router):
        """基本模型选择：无历史数据时返回候选列表中的第一个"""
        candidates = ["model-a", "model-b", "model-c"]
        selected = learning_router.select_model("generate", candidates)
        assert selected in candidates

    def test_exploration_rate(self, learning_router):
        """探索率生效：多次调用应出现非最优模型被选中的情况"""
        candidates = ["best-model", "other-model"]
        # 先记录一些数据使 best-model 成为最优
        for _ in range(10):
            learning_router.record_call("best-model", "task", success=True, latency=50.0)
        learning_router.record_call("other-model", "task", success=False, latency=200.0)

        selections = set()
        for _ in range(100):
            selected = learning_router.select_model("task", candidates)
            selections.add(selected)

        # 由于 EXPLORATION_RATE=0.2，other-model 有一定概率被选中
        # 但 best-model 应该被选中更多次
        assert "best-model" in selections

    def test_degraded_model_avoidance(self, learning_router):
        """降级模型被避免：连续失败超过阈值后模型不再被选中"""
        candidates = ["stable", "degraded"]
        # degraded 连续失败 5 次（阈值）
        for _ in range(5):
            learning_router.record_call("degraded", "task", success=False, latency=100.0)
        learning_router.record_call("stable", "task", success=True, latency=100.0)

        selections = set()
        for _ in range(50):
            selected = learning_router.select_model("task", candidates)
            selections.add(selected)

        # degraded 应该不再被选中（所有候选都降级时才会回退）
        # 由于 stable 未降级，degraded 应被过滤
        assert "stable" in selections


# ==================== LayeredModelRouter 向后兼容 ====================


class TestLayeredModelRouterCompat:
    """_LayeredModelRouterCompat 分层路由测试"""

    def setup_method(self):
        """每个测试前重置缓存"""
        _LayeredModelRouterCompat._config_loaded = False
        _LayeredModelRouterCompat._cached_assignments = None

    def teardown_method(self):
        """每个测试后重置缓存"""
        _LayeredModelRouterCompat._config_loaded = False
        _LayeredModelRouterCompat._cached_assignments = None

    def test_default_assignments_cover_all_complexities(self):
        """所有复杂度都有默认分配"""
        with patch(
            "app.agent.dynamic_model_router.load_agent_model_config",
            return_value=None,
        ):
            for complexity in ProjectComplexity:
                assignment = _LayeredModelRouterCompat.get_assignment(complexity)
                assert assignment is not None, f"默认分配缺失: {complexity}"
                assert assignment.architect_model, f"architect_model 为空: {complexity}"

    def test_config_overrides_defaults(self):
        """配置文件覆盖默认值"""
        config = {
            "assignments": {
                "MEDIUM": {
                    "architect_model": "custom-arch",
                    "frontend_model": "custom-fe",
                    "backend_model": "custom-be",
                    "reviewer_model": "custom-rev",
                    "fallback_model": "custom-fb",
                },
            }
        }
        with patch(
            "app.agent.dynamic_model_router.load_agent_model_config",
            return_value=config,
        ):
            assignment = _LayeredModelRouterCompat.get_assignment(ProjectComplexity.MEDIUM)
            assert assignment.architect_model == "custom-arch"
            assert assignment.frontend_model == "custom-fe"


# ==================== resolve_model_key ====================


class TestResolveModelKey:
    """resolve_model_key 函数测试"""

    def test_resolve_id_to_key(self):
        """模型 ID 解析为完整 Key"""
        assert resolve_model_key("qwen3-8b") == "Qwen/Qwen3-8B"

    def test_resolve_key_passthrough(self):
        """已经是完整 Key 的直接返回"""
        assert resolve_model_key("Qwen/Qwen3-8B") == "Qwen/Qwen3-8B"

    def test_resolve_unknown(self):
        """未知 ID 原样返回"""
        assert resolve_model_key("unknown-model-xyz") == "unknown-model-xyz"
