"""dynamic_model_router 状态更新批次回归（DMR1/DMR6/DMR18）。"""

import asyncio

import pytest

from app.agent import dynamic_model_router as dmr


class TestFallbackChainDedupe:
    def test_helper_removes_duplicates_preserving_order(self):
        assert dmr._dedupe_preserve_order(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]

    def test_default_chain_deduplicated(self, monkeypatch):
        # 多个别名可能解析到同一模型，去重后降级链才真实可用
        monkeypatch.setattr(dmr, "load_agent_model_config", lambda: None)
        monkeypatch.setattr(
            dmr.DynamicModelRouter, "DEFAULT_FALLBACK_ORDER",
            ["model-a", "model-b", "model-a"],
        )

        router = dmr.DynamicModelRouter()

        assert router._fallback_order == ["model-a", "model-b"]

    def test_configured_chain_alias_collision_deduplicated(self, monkeypatch):
        monkeypatch.setattr(
            dmr, "load_agent_model_config",
            lambda: {"fallback_chain": ["key-a", "key-b", "key-c"]},
        )
        # key-a / key-b 是不同的注册 ID，但都指向同一模型
        monkeypatch.setattr(
            dmr, "resolve_model_key",
            lambda m: {"key-a": "model-x", "key-b": "model-x", "key-c": "model-y"}[m],
        )

        router = dmr.DynamicModelRouter()

        assert router._fallback_order == ["model-x", "model-y"]


class TestFailureLatency:
    def test_record_failure_keeps_latency(self):
        metrics = dmr.ModelMetrics(model_name="m")
        metrics.record_success(100.0)
        metrics.record_failure("boom", 200.0)

        assert list(metrics.recent_latencies) == [100.0, 200.0]
        assert metrics.avg_latency_ms == 150.0

    def test_record_failure_without_latency_is_backward_compatible(self):
        metrics = dmr.ModelMetrics(model_name="m")
        metrics.record_failure("boom")

        assert list(metrics.recent_latencies) == []
        assert metrics.failed_requests == 1

    def test_record_call_passes_latency_on_failure(self):
        async def run():
            router = dmr.DynamicModelRouter()
            await router.record_call("m", success=False, latency_ms=250.0, error="boom")
            return router.get_or_create_metrics("m")

        metrics = asyncio.run(run())

        assert list(metrics.recent_latencies) == [250.0]


class TestMappingFailureLogging:
    def test_provider_map_failure_is_logged(self, monkeypatch):
        monkeypatch.setattr(dmr, "_provider_map_cache", None)
        monkeypatch.setattr(dmr, "load_model_config", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("bad config")))
        warnings = []
        monkeypatch.setattr(dmr.logger, "warning", lambda *a, **k: warnings.append(a))

        result = dmr._build_provider_map()

        assert result == {}
        assert warnings, "配置读取失败必须记录日志而非静默返回空映射"

    def test_model_id_map_failure_is_logged(self, monkeypatch):
        monkeypatch.setattr(dmr, "_model_id_key_cache", None)
        monkeypatch.setattr(dmr, "load_model_config", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("bad config")))
        warnings = []
        monkeypatch.setattr(dmr.logger, "warning", lambda *a, **k: warnings.append(a))

        result = dmr._build_model_id_to_key()

        assert result == dmr._FALLBACK_MODEL_ID_TO_KEY
        assert warnings, "配置读取失败必须记录日志而非静默返回兜底映射"
