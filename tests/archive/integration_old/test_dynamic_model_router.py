"""
动态模型路由集成测试

测试场景：
1. 动态路由器单例初始化
2. 模型指标记录（成功/失败）
3. 健康分数计算
4. 熔断机制
5. 动态路由选择
6. 并发安全
"""

import pytest
import asyncio
import time
from app.agent.dynamic_model_router import DynamicModelRouter, ModelMetrics, get_dynamic_router


@pytest.fixture
def router():
 """创建动态路由器实例"""
 return DynamicModelRouter()


@pytest.fixture
async def global_router():
 """获取全局路由器单例"""
 return await get_dynamic_router()


class TestModelMetrics:
 """模型指标测试"""

 def test_initial_state(self):
 metrics = ModelMetrics(model_name="test-model")
 assert metrics.success_rate == 1.0
 assert metrics.avg_latency_ms == 0.0
 assert metrics.health_score == 100.0
 assert metrics.consecutive_failures == 0

 def test_record_success(self):
 metrics = ModelMetrics(model_name="test-model")
 metrics.record_success(100.0)
 assert metrics.total_requests == 1
 assert metrics.successful_requests == 1
 assert metrics.success_rate == 1.0
 assert metrics.avg_latency_ms == 100.0
 assert metrics.consecutive_failures == 0

 def test_record_failure(self):
 metrics = ModelMetrics(model_name="test-model")
 metrics.record_failure("timeout")
 assert metrics.total_requests == 1
 assert metrics.failed_requests == 1
 assert metrics.success_rate == 0.0
 assert metrics.consecutive_failures == 1

 def test_health_score_degradation(self):
 metrics = ModelMetrics(model_name="test-model")

 # 初始健康
 assert metrics.health_score == 100.0

 # 记录一些成功请求
 for i in range(10):
 metrics.record_success(200.0 + i * 10)

 # 健康分数应该仍然很高
 assert metrics.health_score > 80.0

 # 记录失败请求
 metrics.record_failure("error")
 assert metrics.health_score < 100.0

 def test_circuit_breaker(self):
 metrics = ModelMetrics(model_name="test-model")

 # 连续 3 次失败应该触发熔断
 for _ in range(3):
 metrics.record_failure("error")

 assert metrics.consecutive_failures == 3
 assert metrics.health_score == 0 # 熔断

 def test_recovery_after_success(self):
 metrics = ModelMetrics(model_name="test-model")

 # 先失败
 metrics.record_failure("error")
 assert metrics.consecutive_failures == 1

 # 然后成功，应该重置连续失败计数
 metrics.record_success(100.0)
 assert metrics.consecutive_failures == 0

 def test_p95_latency(self):
 metrics = ModelMetrics(model_name="test-model")

 # 记录 20 个不同延迟的请求
 for i in range(20):
 metrics.record_success(100.0 + i * 10)

 # P95 应该接近最大值
 assert metrics.p95_latency_ms > metrics.avg_latency_ms


class TestDynamicModelRouter:
 """动态路由器测试"""

 @pytest.mark.asyncio
 async def test_singleton(self, global_router):
 """测试全局单例"""
 router2 = await get_dynamic_router()
 assert global_router is router2

 @pytest.mark.asyncio
 async def test_get_or_create_metrics(self, router):
 metrics = router.get_or_create_metrics("model-a")
 assert metrics.model_name == "model-a"

 # 再次获取应该返回同一个实例
 metrics2 = router.get_or_create_metrics("model-a")
 assert metrics is metrics2

 @pytest.mark.asyncio
 async def test_record_call_success(self, router):
 await router.record_call("model-a", success=True, latency_ms=150.0)
 metrics = router.get_or_create_metrics("model-a")
 assert metrics.successful_requests == 1
 assert metrics.avg_latency_ms == 150.0

 @pytest.mark.asyncio
 async def test_record_call_failure(self, router):
 await router.record_call("model-b", success=False, latency_ms=5000.0, error="timeout")
 metrics = router.get_or_create_metrics("model-b")
 assert metrics.failed_requests == 1
 assert metrics.consecutive_failures == 1

 @pytest.mark.asyncio
 async def test_get_best_model_single_candidate(self, router):
 best = await router.get_best_model(["model-a"])
 assert best == "model-a"

 @pytest.mark.asyncio
 async def test_get_best_model_multiple_candidates(self, router):
 # 模拟不同健康状态的模型
 await router.record_call("model-a", success=True, latency_ms=100.0)
 await router.record_call("model-a", success=True, latency_ms=120.0)
 await router.record_call("model-b", success=False, latency_ms=5000.0, error="timeout")

 best = await router.get_best_model(["model-a", "model-b"])

 # model-a 应该被选中，因为它更健康
 assert best == "model-a"

 @pytest.mark.asyncio
 async def test_circuit_breaker_routing(self, router):
 # 让 model-a 熔断
 for _ in range(3):
 await router.record_call("model-a", success=False, latency_ms=1000.0)

 # model-b 健康
 await router.record_call("model-b", success=True, latency_ms=100.0)

 best = await router.get_best_model(["model-a", "model-b"])

 # 应该绕过熔断的 model-a
 assert best == "model-b"

 @pytest.mark.asyncio
 async def test_fallback_when_all_circuit_broken(self, router):
 # 让所有候选模型熔断
 for model in ["model-a", "model-b"]:
 for _ in range(3):
 await router.record_call(model, success=False, latency_ms=1000.0)

 best = await router.get_best_model(["model-a", "model-b"])

 # 应该返回降级模型
 assert best in router._fallback_order

 @pytest.mark.asyncio
 async def test_health_report(self, router):
 await router.record_call("model-a", success=True, latency_ms=100.0)
 await router.record_call("model-b", success=False, latency_ms=5000.0)

 report = await router.get_model_health_report()

 assert "model-a" in report
 assert "model-b" in report
 assert report["model-a"]["status"] == "healthy"
 assert report["model-b"]["status"] in ["degraded", "circuit_breaker"]

 @pytest.mark.asyncio
 async def test_reset_metrics(self, router):
 await router.record_call("model-a", success=True, latency_ms=100.0)
 assert router.get_or_create_metrics("model-a").total_requests == 1

 await router.reset_metrics("model-a")
 assert "model-a" not in router._metrics

 @pytest.mark.asyncio
 async def test_reset_all_metrics(self, router):
 await router.record_call("model-a", success=True, latency_ms=100.0)
 await router.record_call("model-b", success=True, latency_ms=200.0)

 await router.reset_metrics()
 assert len(router._metrics) == 0


class TestConcurrencySafety:
 """并发安全测试"""

 @pytest.mark.asyncio
 async def test_concurrent_record_calls(self, router):
 """并发记录调用应该不会导致数据竞争"""
 async def record_many(model_name, count):
 tasks = [
 router.record_call(model_name, success=True, latency_ms=100.0 + i)
 for i in range(count)
 ]
 await asyncio.gather(*tasks)

 # 并发记录 100 次
 await asyncio.gather(
 record_many("model-a", 100),
 record_many("model-b", 100)
 )

 metrics_a = router.get_or_create_metrics("model-a")
 metrics_b = router.get_or_create_metrics("model-b")

 assert metrics_a.total_requests == 100
 assert metrics_b.total_requests == 100

 @pytest.mark.asyncio
 async def test_concurrent_best_model_selection(self, router):
 """并发选择最佳模型应该不会导致崩溃"""
 # 预热一些数据
 for i in range(10):
 await router.record_call("model-a", success=True, latency_ms=100.0 + i * 10)
 await router.record_call("model-b", success=True, latency_ms=150.0 + i * 10)

 async def select_best():
 return await router.get_best_model(["model-a", "model-b"])

 # 并发选择 50 次
 results = await asyncio.gather(*[select_best() for _ in range(50)])

 # 所有结果都应该是有效的模型名称
 assert all(r in ["model-a", "model-b"] for r in results)


class TestDynamicRouterIntegration:
 """与 ModelRouter 集成测试"""

 @pytest.mark.asyncio
 async def test_route_dynamic(self):
 from app.agent.multi_model_agent import ModelRouter, TaskType

 # 预热一些指标
 router = await get_dynamic_router()
 await router.record_call("qwen3-8b", success=True, latency_ms=200.0)
 await router.record_call("deepseek-r1-qwen3-8b", success=True, latency_ms=300.0)

 # 动态路由应该返回一个有效的模型
 model = await ModelRouter.route_dynamic(TaskType.CODE_GENERATION)
 assert model is not None
 assert model.key in ["qwen3-8b", "deepseek-r1-qwen3-8b", "qwen2.5-7b"]
