import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent import dynamic_model_router as dmr


@pytest.fixture(autouse=True)
def _restore_mapping_globals():
    """还原模块级映射缓存，避免测试之间互相污染。"""
    saved = (
        dmr.MODEL_ID_TO_KEY,
        dmr.MODEL_PROVIDER_MAP,
        dmr.MODEL_KEY_TO_ID,
        dmr._model_id_key_cache,
        dmr._provider_map_cache,
    )
    yield
    (
        dmr.MODEL_ID_TO_KEY,
        dmr.MODEL_PROVIDER_MAP,
        dmr.MODEL_KEY_TO_ID,
        dmr._model_id_key_cache,
        dmr._provider_map_cache,
    ) = saved


# ---------------------------------------------------------------------------
# module-level helpers
# ---------------------------------------------------------------------------

def test_dedupe_skips_empty_values():
    assert dmr._dedupe_preserve_order(["", "a", "", "b", "a"]) == ["a", "b"]


def test_build_provider_map_defaults_unknown_provider(monkeypatch):
    monkeypatch.setattr(dmr, "_provider_map_cache", None)
    monkeypatch.setattr(
        dmr,
        "load_model_config",
        lambda path: {
            "models": {
                "m1": {"name": "Model One", "provider": "unknown"},
                "m2": {"name": "", "provider": "dashscope"},
            }
        },
    )

    result = dmr._build_provider_map()

    assert result["m1"] == dmr.ModelProvider.SILICONFLOW
    assert result["Model One"] == dmr.ModelProvider.SILICONFLOW
    assert result["m2"] == dmr.ModelProvider.DASHSCOPE
    assert dmr._provider_map_cache is result


def test_build_provider_map_uses_cache_on_error(monkeypatch):
    monkeypatch.setattr(dmr, "_provider_map_cache", {"cached": "p"})
    monkeypatch.setattr(
        dmr, "load_model_config", lambda path: (_ for _ in ()).throw(ValueError("bad"))
    )
    warnings = []
    monkeypatch.setattr(dmr.logger, "warning", lambda *a, **k: warnings.append(a))

    assert dmr._build_provider_map() == {"cached": "p"}
    assert warnings


def test_build_model_id_to_key(monkeypatch):
    monkeypatch.setattr(dmr, "_model_id_key_cache", None)
    monkeypatch.setattr(
        dmr,
        "load_model_config",
        lambda path: {"models": {"id1": {"name": "Key/One"}, "id2": {"name": ""}}},
    )

    assert dmr._build_model_id_to_key() == {"id1": "Key/One"}
    assert dmr._model_id_key_cache == {"id1": "Key/One"}


def test_build_model_id_to_key_uses_cache_on_error(monkeypatch):
    monkeypatch.setattr(dmr, "_model_id_key_cache", {"cached": "v"})
    monkeypatch.setattr(
        dmr, "load_model_config", lambda path: (_ for _ in ()).throw(ValueError("bad"))
    )
    warnings = []
    monkeypatch.setattr(dmr.logger, "warning", lambda *a, **k: warnings.append(a))

    assert dmr._build_model_id_to_key() == {"cached": "v"}
    assert warnings


def test_get_model_id_to_key_lazy_build(monkeypatch):
    monkeypatch.setattr(dmr, "_model_id_key_cache", None)
    monkeypatch.setattr(
        dmr, "load_model_config", lambda path: {"models": {"id": {"name": "Key"}}}
    )

    assert dmr.get_model_id_to_key() == {"id": "Key"}
    assert dmr.get_model_id_to_key() == {"id": "Key"}


def test_get_model_id_to_key_fallback(monkeypatch):
    monkeypatch.setattr(dmr, "_model_id_key_cache", None)

    def boom(path):
        raise ValueError("bad")

    monkeypatch.setattr(dmr, "load_model_config", boom)

    assert dmr.get_model_id_to_key() == dmr._FALLBACK_MODEL_ID_TO_KEY


def test_get_model_provider_map_lazy_build(monkeypatch):
    monkeypatch.setattr(dmr, "_provider_map_cache", None)
    monkeypatch.setattr(
        dmr, "load_model_config", lambda path: {"models": {"id": {"name": "Name"}}}
    )

    assert dmr.get_model_provider_map()["id"] == dmr.ModelProvider.SILICONFLOW
    assert dmr.get_model_provider_map()["id"] == dmr.ModelProvider.SILICONFLOW


def test_get_model_provider_map_empty_fallback(monkeypatch):
    monkeypatch.setattr(dmr, "_provider_map_cache", None)

    def boom(path):
        raise ValueError("bad")

    monkeypatch.setattr(dmr, "load_model_config", boom)

    assert dmr.get_model_provider_map() == {}


def test_invalidate_model_mapping_cache_rebuilds(monkeypatch):
    reloaded = []
    monkeypatch.setattr(
        dmr, "_build_model_id_to_key", lambda: {"id": "Key"}
    )
    monkeypatch.setattr(
        dmr, "_build_provider_map", lambda: {"id": "provider"}
    )
    monkeypatch.setattr(
        "app.utils.aicloud.provider_router.reload_provider_map",
        lambda: reloaded.append(True),
    )

    dmr.invalidate_model_mapping_cache()

    assert dmr.MODEL_ID_TO_KEY == {"id": "Key"}
    assert dmr.MODEL_PROVIDER_MAP == {"id": "provider"}
    assert dmr.MODEL_KEY_TO_ID == {"Key": "id"}
    assert reloaded


def test_invalidate_model_mapping_cache_swallows_reload_error(monkeypatch):
    monkeypatch.setattr(dmr, "_build_model_id_to_key", lambda: {})
    monkeypatch.setattr(dmr, "_build_provider_map", lambda: {})

    def boom():
        raise RuntimeError("no router")

    monkeypatch.setattr("app.utils.aicloud.provider_router.reload_provider_map", boom)

    dmr.invalidate_model_mapping_cache()


def test_resolve_model_key_passthrough_and_mapping(monkeypatch):
    monkeypatch.setattr(dmr, "MODEL_ID_TO_KEY", {"id": "Key"})

    assert dmr.resolve_model_key("Vendor/Model") == "Vendor/Model"
    assert dmr.resolve_model_key("id") == "Key"
    assert dmr.resolve_model_key("unknown") == "unknown"


def test_load_agent_model_config_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(dmr, "AGENT_MODEL_CONFIG_PATH", str(tmp_path / "missing.yaml"))

    assert dmr.load_agent_model_config() is None


def test_load_agent_model_config_success(monkeypatch, tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("x: 1\n", encoding="utf-8")
    monkeypatch.setattr(dmr, "AGENT_MODEL_CONFIG_PATH", str(path))
    monkeypatch.setattr(dmr, "load_model_config", lambda p: {"roles": {}})

    assert dmr.load_agent_model_config() == {"roles": {}}


def test_load_agent_model_config_swallows_error(monkeypatch, tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("x: 1\n", encoding="utf-8")
    monkeypatch.setattr(dmr, "AGENT_MODEL_CONFIG_PATH", str(path))

    def boom(p):
        raise ValueError("bad")

    monkeypatch.setattr(dmr, "load_model_config", boom)
    warnings = []
    monkeypatch.setattr(dmr.logger, "warning", lambda *a, **k: warnings.append(a))

    assert dmr.load_agent_model_config() is None
    assert warnings


def test_save_agent_model_config_success(monkeypatch, tmp_path):
    monkeypatch.setattr(
        dmr, "AGENT_MODEL_CONFIG_PATH", str(tmp_path / "nested" / "config.yaml")
    )
    saved = []
    monkeypatch.setattr(dmr, "save_model_config", lambda p, c: saved.append((p, c)))

    assert dmr.save_agent_model_config({"a": 1}) is True
    assert saved


def test_save_agent_model_config_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        dmr, "AGENT_MODEL_CONFIG_PATH", str(tmp_path / "config.yaml")
    )

    def boom(p, c):
        raise OSError("readonly")

    monkeypatch.setattr(dmr, "save_model_config", boom)
    errors = []
    monkeypatch.setattr(dmr.logger, "error", lambda *a, **k: errors.append(a))

    assert dmr.save_agent_model_config({}) is False
    assert errors


def test_noop_lock_protocol():
    lock = dmr._NoopLock()

    assert lock.acquire() is True
    lock.release()
    with lock as entered:
        assert entered is lock


# ---------------------------------------------------------------------------
# ModelPerformanceTracker
# ---------------------------------------------------------------------------

@pytest.fixture
def tracker(tmp_path):
    instance = dmr.ModelPerformanceTracker(
        db_path=str(tmp_path / "perf.db"), sync_lock_factory=dmr._NoopLock
    )
    yield instance
    instance.close()


def test_tracker_record_new_success_and_failure(tracker):
    tracker._record_call_sync("m", "generate", True, 100.0)
    tracker._record_call_sync("m", "generate", False, 300.0)

    cursor = tracker._conn.execute(
        "SELECT success_rate, avg_latency, total_calls, consecutive_failures "
        "FROM performance WHERE model_name='m' AND task_type='generate'"
    )
    rate, latency, calls, cf = cursor.fetchone()

    assert calls == 2
    assert rate == pytest.approx(0.5)
    assert latency == pytest.approx(200.0)
    assert cf == 1


def test_tracker_record_success_resets_consecutive_failures(tracker):
    tracker._record_call_sync("m", "generate", False, 10.0)
    tracker._record_call_sync("m", "generate", False, 10.0)
    tracker._record_call_sync("m", "generate", True, 10.0)

    cursor = tracker._conn.execute(
        "SELECT consecutive_failures FROM performance WHERE model_name='m'"
    )
    assert cursor.fetchone()[0] == 0


@pytest.mark.asyncio
async def test_tracker_record_call_async(tracker):
    await tracker.record_call("m", "generate", True, 50.0)

    assert tracker.get_total_records() == 1


def test_tracker_get_best_model_filters_circuit_breaker(tracker):
    for index in range(6):
        tracker._record_call_sync("broken", "t", False, 10.0)
    tracker._record_call_sync("ok", "t", True, 20.0)

    assert tracker.get_best_model("t") == ["ok"]


def test_tracker_get_unified_best_model_without_history(tracker):
    metrics = {
        "a": dmr.ModelMetrics("a"),
        "b": dmr.ModelMetrics("b"),
        "c": dmr.ModelMetrics("c"),
    }

    assert tracker.get_unified_best_model("t", metrics, top_k=2) == ["a", "b"]


def test_tracker_get_unified_best_model_combines_scores(tracker):
    tracker._record_call_sync("history", "t", True, 10.0)
    realtime = {
        "history": dmr.ModelMetrics("history"),
        "fresh": dmr.ModelMetrics("fresh"),
    }
    realtime["fresh"].record_success(10.0)

    result = tracker.get_unified_best_model("t", realtime, top_k=2)

    assert set(result) == {"history", "fresh"}


def test_tracker_get_unified_best_model_historical_without_realtime(tracker):
    tracker._record_call_sync("history", "t", True, 10.0)
    realtime = {"fresh": dmr.ModelMetrics("fresh")}
    realtime["fresh"].record_success(10.0)

    result = tracker.get_unified_best_model("t", realtime, top_k=2)

    assert set(result) == {"history", "fresh"}


def test_tracker_cleanup_handles_missing_row(monkeypatch, tmp_path):
    class _Cursor:
        def fetchone(self):
            return None

    class _Conn:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params=()):
            self.executed.append(sql)
            if "pragma_page_count" in sql:
                return _Cursor()
            return self

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(dmr.sqlite3, "connect", lambda *a, **k: _Conn())
    instance = dmr.ModelPerformanceTracker(db_path=str(tmp_path / "x.db"))

    instance.close()


def test_tracker_cleanup_downsizes_large_db(monkeypatch, tmp_path):
    class _Cursor:
        def fetchone(self):
            return (dmr.ModelPerformanceTracker.MAX_DB_SIZE_BYTES + 1,)

    class _Conn:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params=()):
            self.executed.append(sql)
            if "pragma_page_count" in sql:
                return _Cursor()
            return self

        def commit(self):
            pass

        def close(self):
            pass

    conn = _Conn()
    monkeypatch.setattr(dmr.sqlite3, "connect", lambda *a, **k: conn)
    dmr.ModelPerformanceTracker(db_path=str(tmp_path / "x.db"))

    assert any("VACUUM" in sql for sql in conn.executed)


def test_tracker_cleanup_swallows_size_error(monkeypatch, tmp_path):
    class _Conn:
        def execute(self, sql, params=()):
            if "pragma_page_count" in sql:
                raise RuntimeError("no pragma")
            return self

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(dmr.sqlite3, "connect", lambda *a, **k: _Conn())
    debug = []
    monkeypatch.setattr(dmr.logger, "debug", lambda *a, **k: debug.append(a))

    dmr.ModelPerformanceTracker(db_path=str(tmp_path / "x.db"))

    assert debug


# ---------------------------------------------------------------------------
# LearningRouter
# ---------------------------------------------------------------------------

class _FakeTracker:
    def __init__(self, best=None, total=0):
        self.best = best or []
        self.total = total
        self.recorded = []

    def get_best_model(self, task_type, top_k=3):
        return self.best[:top_k]

    def get_total_records(self):
        return self.total

    def _record_call_sync(self, model, task_type, success, latency):
        self.recorded.append((model, task_type, success, latency))


def test_learning_router_empty_candidates():
    router = dmr.LearningRouter(tracker=_FakeTracker())

    assert router.select_model("t", []) == dmr.DEFAULT_FAST_MODEL


def test_learning_router_prefers_ranked_model(monkeypatch):
    router = dmr.LearningRouter(tracker=_FakeTracker(best=["b"]))
    monkeypatch.setattr(dmr.random, "random", lambda: 1.0)

    assert router.select_model("t", ["a", "b"]) == "b"


def test_learning_router_single_ranked_model(monkeypatch):
    router = dmr.LearningRouter(tracker=_FakeTracker(best=[]))

    assert router.select_model("t", ["a"]) == "a"


def test_learning_router_explores_ranked_tail(monkeypatch):
    router = dmr.LearningRouter(tracker=_FakeTracker(best=[]))
    monkeypatch.setattr(dmr.random, "random", lambda: 0.0)
    monkeypatch.setattr(dmr.random, "choice", lambda seq: seq[-1])

    assert router.select_model("t", ["a", "b"]) == "b"


def test_learning_router_exploration_without_tail(monkeypatch):
    router = dmr.LearningRouter(tracker=_FakeTracker(best=["a", "b"]))
    monkeypatch.setattr(dmr.random, "random", lambda: 0.0)
    # ranked has one element after removing head only when tail empty
    router._tracker.best = ["a"]

    assert router.select_model("t", ["a", "b"]) in {"a", "b"}


def test_learning_router_degraded_all_resets(monkeypatch):
    tracker = _FakeTracker(best=[])
    router = dmr.LearningRouter(tracker=tracker)
    router._degraded_models["t"] = {"a": dmr.LearningRouter.DEGRADATION_THRESHOLD}
    monkeypatch.setattr(dmr.random, "random", lambda: 1.0)

    assert router.select_model("t", ["a"]) == "a"
    assert "t" not in router._degraded_models


def test_learning_router_degraded_candidate_excluded(monkeypatch):
    tracker = _FakeTracker(best=[])
    router = dmr.LearningRouter(tracker=tracker)
    router._degraded_models["t"] = {"a": dmr.LearningRouter.DEGRADATION_THRESHOLD}
    monkeypatch.setattr(dmr.random, "random", lambda: 1.0)

    assert router.select_model("t", ["a", "b"]) == "b"


def test_learning_router_record_failure_and_success_cleanup():
    tracker = _FakeTracker()
    router = dmr.LearningRouter(tracker=tracker)

    router.record_call("a", "t", False, 1.0)
    assert router._degraded_models["t"]["a"] == 1

    router.record_call("a", "t", True, 1.0)
    assert "t" not in router._degraded_models
    assert tracker.recorded


def test_learning_router_success_when_no_degraded_entry():
    tracker = _FakeTracker()
    router = dmr.LearningRouter(tracker=tracker)

    router.record_call("a", "t", True, 1.0)

    assert router._degraded_models == {}


def test_learning_router_repeated_failure_and_partial_cleanup():
    tracker = _FakeTracker()
    router = dmr.LearningRouter(tracker=tracker)

    router.record_call("a", "t", False, 1.0)
    router.record_call("b", "t", False, 1.0)
    router.record_call("a", "t", True, 1.0)

    assert router._degraded_models["t"] == {"b": 1}


def test_learning_router_best_model_outside_eligible(monkeypatch):
    tracker = _FakeTracker(best=["ghost"])
    router = dmr.LearningRouter(tracker=tracker)
    monkeypatch.setattr(dmr.random, "random", lambda: 1.0)

    assert router.select_model("t", ["a"]) == "a"


def test_learning_router_has_sufficient_data():
    assert dmr.LearningRouter(tracker=_FakeTracker(total=11)).has_sufficient_data() is True
    assert dmr.LearningRouter(tracker=_FakeTracker(total=11)).has_sufficient_data() is True
    assert dmr.LearningRouter(tracker=_FakeTracker(total=10)).has_sufficient_data() is False


@pytest.mark.asyncio
async def test_get_learning_router_singleton(monkeypatch):
    monkeypatch.setattr(dmr, "_learning_router", None)

    first = await dmr.get_learning_router()
    second = await dmr.get_learning_router()

    assert first is second
    first._tracker.close()


# ---------------------------------------------------------------------------
# ModelMetrics
# ---------------------------------------------------------------------------

def test_metrics_defaults_and_success_rate():
    metrics = dmr.ModelMetrics("m")

    assert metrics.success_rate == 1.0
    assert metrics.avg_latency_ms == 0.0
    metrics.record_failure()
    assert metrics.success_rate == 0.0


def test_metrics_p95_with_few_samples_returns_average():
    metrics = dmr.ModelMetrics("m")
    for value in (10.0, 20.0):
        metrics.record_success(value)

    assert metrics.p95_latency_ms == 15.0


def test_metrics_p95_with_many_samples():
    metrics = dmr.ModelMetrics("m")
    for value in range(1, 101):
        metrics.record_success(float(value))

    assert metrics.p95_latency_ms == 96.0


def test_metrics_health_score_zero_latency_and_queue():
    metrics = dmr.ModelMetrics("m")

    assert metrics.health_score == 100.0


def test_metrics_health_score_with_latency_and_queue():
    metrics = dmr.ModelMetrics("m")
    metrics.record_success(5000.0)
    metrics.active_requests = 10

    score = metrics.health_score

    assert score == pytest.approx(50 + 15 + 10)


def test_metrics_health_score_latency_floor():
    metrics = dmr.ModelMetrics("m")
    metrics.record_success(20000.0)

    assert metrics.health_score == 70.0


def test_metrics_health_score_circuit_breaker():
    metrics = dmr.ModelMetrics("m")
    for _ in range(3):
        metrics.record_failure()

    assert metrics.health_score == 0


def test_metrics_start_request_and_record_success_resets():
    metrics = dmr.ModelMetrics("m")
    metrics.start_request()
    metrics.start_request()
    assert metrics.active_requests == 2

    metrics.record_success(10.0)
    assert metrics.active_requests == 1
    assert metrics.consecutive_failures == 0
    assert metrics.last_success_time is not None


def test_metrics_record_failure_never_negative_queue():
    metrics = dmr.ModelMetrics("m")
    metrics.record_failure("boom")

    assert metrics.active_requests == 0
    assert metrics.last_error_time is not None


# ---------------------------------------------------------------------------
# DynamicModelRouter
# ---------------------------------------------------------------------------

def _router(monkeypatch, config=None):
    monkeypatch.setattr(dmr, "load_agent_model_config", lambda: config)
    return dmr.DynamicModelRouter()


def test_fallback_chain_v2_config(monkeypatch):
    router = _router(
        monkeypatch,
        {"fallback_chains": {"custom": ["a", "b", "a"]}},
    )

    assert router._load_fallback_chain("custom") == ["a", "b"]


def test_fallback_chain_v2_empty_falls_back(monkeypatch):
    router = _router(monkeypatch, {"fallback_chains": {"custom": []}})

    assert router._load_fallback_chain("custom") == dmr._dedupe_preserve_order(
        dmr.DynamicModelRouter.DEFAULT_FALLBACK_ORDER
    )


def test_fallback_chain_empty_config(monkeypatch):
    router = _router(monkeypatch, {"fallback_chain": [], "fallback_chains": {"default": []}})

    assert router._fallback_order


def test_fallback_chain_config_without_chain_keys(monkeypatch):
    router = _router(monkeypatch, {"roles": {}})

    assert router._fallback_order == dmr._dedupe_preserve_order(
        dmr.DynamicModelRouter.DEFAULT_FALLBACK_ORDER
    )


def test_reload_fallback_chain(monkeypatch):
    router = _router(monkeypatch, None)
    monkeypatch.setattr(dmr, "load_agent_model_config", lambda: {"fallback_chain": ["x"]})

    router.reload_fallback_chain()

    assert router._fallback_order == [dmr.resolve_model_key("x")]


@pytest.mark.asyncio
async def test_get_best_model_empty_candidates(monkeypatch):
    router = _router(monkeypatch, None)

    assert await router.get_best_model([]) == router._fallback_order[0]


@pytest.mark.asyncio
async def test_get_best_model_all_circuit_broken_uses_healthy_fallback(monkeypatch):
    router = _router(monkeypatch, None)
    router._fallback_order = ["a", "b"]
    router.get_or_create_metrics("candidate").consecutive_failures = 3
    router.get_or_create_metrics("a").consecutive_failures = 3

    assert await router.get_best_model(["candidate"]) == "b"


@pytest.mark.asyncio
async def test_get_best_model_all_broken_forces_first(monkeypatch):
    router = _router(monkeypatch, None)
    router._fallback_order = ["a", "b"]
    for name in ("candidate", "a", "b"):
        router.get_or_create_metrics(name).consecutive_failures = 3

    assert await router.get_best_model(["candidate"]) == "a"


@pytest.mark.asyncio
async def test_get_best_model_healthy(monkeypatch):
    router = _router(monkeypatch, None)
    router.get_or_create_metrics("slow").record_success(5000.0)
    router.get_or_create_metrics("fast").record_success(10.0)

    assert await router.get_best_model(["slow", "fast"], "generate") == "fast"


@pytest.mark.asyncio
async def test_record_start_and_reset(monkeypatch):
    router = _router(monkeypatch, None)
    await router.start_call("m")
    await router.record_call("m", True, 10.0)

    assert router.get_or_create_metrics("m").total_requests == 1

    await router.reset_metrics("m")
    assert "m" not in router._metrics

    await router.start_call("n")
    await router.reset_metrics()
    assert router._metrics == {}

    await router.start_call("missing")
    await router.reset_metrics("missing")
    assert "missing" not in router._metrics


def test_get_assignment_applies_circuit_breaker(monkeypatch):
    router = _router(monkeypatch, None)
    assignment = dmr.ModelAssignment("arch", "front", "back", "review", "fallback")
    monkeypatch.setattr(dmr, "_load_roles_assignment", lambda: assignment)

    assert router.get_assignment().architect_model == "arch"


@pytest.mark.asyncio
async def test_health_report_statuses(monkeypatch):
    router = _router(monkeypatch, None)
    router.get_or_create_metrics("healthy")
    degraded = router.get_or_create_metrics("degraded")
    degraded.record_success(5000.0)
    degraded.active_requests = 15
    broken = router.get_or_create_metrics("broken")
    for _ in range(3):
        broken.record_failure()

    report = await router.get_model_health_report()

    assert report["healthy"]["status"] == "healthy"
    assert report["degraded"]["status"] == "degraded"
    assert report["broken"]["status"] == "circuit_breaker"


def test_apply_circuit_breaker(monkeypatch):
    router = _router(monkeypatch, None)
    assignment = dmr.ModelAssignment("arch", "front", "back", "review", "fallback")
    router.get_or_create_metrics("arch").consecutive_failures = 2
    router.get_or_create_metrics("fallback").consecutive_failures = 5

    result = router._apply_circuit_breaker(assignment)

    assert result.architect_model == "fallback"
    assert result.fallback_model == "fallback"


@pytest.mark.asyncio
async def test_get_assignment_with_learning_sufficient_data(monkeypatch):
    router = _router(monkeypatch, None)
    assignment = dmr.ModelAssignment("arch", "front", "back", "review", "fallback")
    monkeypatch.setattr(dmr, "_load_roles_assignment", lambda: assignment)

    class _Learning:
        def has_sufficient_data(self):
            return True

        def select_model(self, task_type, models):
            return models[0]

    result = await router.get_assignment_with_learning(learning_router=_Learning())

    assert result.architect_model == "arch"


@pytest.mark.asyncio
async def test_get_assignment_with_learning_insufficient_data(monkeypatch):
    router = _router(monkeypatch, None)
    assignment = dmr.ModelAssignment("arch", "front", "back", "review", "fallback")
    monkeypatch.setattr(dmr, "_load_roles_assignment", lambda: assignment)

    class _Learning:
        def has_sufficient_data(self):
            return False

    monkeypatch.setattr(dmr, "get_learning_router", lambda: _noop_coro(_Learning()))

    result = await router.get_assignment_with_learning()

    assert result.architect_model == "arch"


async def _noop_coro(value):
    return value


@pytest.mark.asyncio
async def test_get_dynamic_router_singleton(monkeypatch):
    monkeypatch.setattr(dmr, "_dynamic_router", None)

    first = await dmr.get_dynamic_router()
    second = await dmr.get_dynamic_router()

    assert first is second
    assert dmr.get_dynamic_router_sync() is first


@pytest.mark.asyncio
async def test_get_dynamic_router_double_check_race(monkeypatch):
    monkeypatch.setattr(dmr, "_dynamic_router", None)
    sentinel = dmr.DynamicModelRouter()

    class _Lock:
        async def __aenter__(self):
            dmr._dynamic_router = sentinel
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(dmr, "_router_lock", _Lock())

    assert await dmr.get_dynamic_router() is sentinel


def test_get_dynamic_router_sync_creates(monkeypatch):
    monkeypatch.setattr(dmr, "_dynamic_router", None)

    assert isinstance(dmr.get_dynamic_router_sync(), dmr.DynamicModelRouter)


def test_compat_router_caches_assignments(monkeypatch):
    dmr._LayeredModelRouterCompat._config_loaded = False
    dmr._LayeredModelRouterCompat._cached_assignments = None
    monkeypatch.setattr(
        dmr,
        "load_agent_model_config",
        lambda: {"assignments": {"SMALL": {"architect_model": "custom"}}},
    )
    from app.agent.complexity import ProjectComplexity

    result = dmr._LayeredModelRouterCompat.get_assignment(ProjectComplexity.SMALL)

    assert result.architect_model == dmr.resolve_model_key("custom")
    assert dmr._LayeredModelRouterCompat.get_assignment(ProjectComplexity.SMALL) is result

    dmr._LayeredModelRouterCompat.reload_config()
    assert dmr._LayeredModelRouterCompat._config_loaded is False


def test_compat_router_enterprise_maps_to_large(monkeypatch):
    dmr._LayeredModelRouterCompat._config_loaded = False
    dmr._LayeredModelRouterCompat._cached_assignments = None
    monkeypatch.setattr(dmr, "load_agent_model_config", lambda: None)
    from app.agent.complexity import ProjectComplexity

    result = dmr._LayeredModelRouterCompat.get_assignment(ProjectComplexity.ENTERPRISE)

    assert result.architect_model == dmr.DEFAULT_ARCHITECT_MODEL


def test_load_roles_assignment_from_cache(monkeypatch):
    monkeypatch.setattr(
        dmr,
        "_roles_cache",
        {"architect": "a", "frontend": "f", "backend": "b", "reviewer": "r", "fallback": "x"},
    )

    result = dmr._load_roles_assignment()

    assert result.reviewer_model == "r"


def test_load_roles_assignment_from_config(monkeypatch):
    monkeypatch.setattr(dmr, "_roles_cache", None)
    monkeypatch.setattr(
        dmr,
        "load_agent_model_config",
        lambda: {"roles": {"architect": "custom", "frontend": "front"}},
    )

    result = dmr._load_roles_assignment()

    assert result.frontend_model == dmr.resolve_model_key("front")
    assert result.fallback_model == dmr._DEFAULT_ROLES["fallback"]
    assert dmr._roles_cache is not None


def test_load_roles_assignment_defaults(monkeypatch):
    monkeypatch.setattr(dmr, "_roles_cache", None)
    monkeypatch.setattr(dmr, "load_agent_model_config", lambda: None)

    result = dmr._load_roles_assignment()

    assert result.architect_model == dmr._DEFAULT_ROLES["architect"]


def test_reload_roles_config(monkeypatch):
    monkeypatch.setattr(dmr, "_roles_cache", {"x": "y"})
    monkeypatch.setattr(dmr, "invalidate_model_mapping_cache", lambda: None)
    monkeypatch.setattr(dmr, "load_agent_model_config", lambda: None)

    result = dmr.reload_roles_config()

    assert result.architect_model == dmr._DEFAULT_ROLES["architect"]


# ---------------------------------------------------------------------------
# health-aware routing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_aware_empty_candidates():
    assert await dmr.get_best_model_with_health_awareness([]) == dmr.DEFAULT_FAST_MODEL


@pytest.mark.asyncio
async def test_health_aware_disabled_uses_dynamic_router(monkeypatch):
    class _Router:
        async def get_best_model(self, candidates, task_type):
            return "picked"

    monkeypatch.setattr(dmr, "get_dynamic_router", lambda: _noop_coro(_Router()))

    assert await dmr.get_best_model_with_health_awareness(["a"]) == "picked"


@pytest.mark.asyncio
async def test_health_aware_overloaded_selects_lightest(monkeypatch):
    class _Monitor:
        async def get_load_snapshot(self):
            return {"load": 1.0}

        def is_system_overloaded(self, threshold):
            return True

        def get_model_load_score(self, model):
            return {"a": 0.9, "b": 0.1}[model]

    monkeypatch.setattr(dmr, "system_load_monitor", _Monitor())

    config = dmr.RoutingConfig(enable_health_aware_routing=True)
    result = await dmr.get_best_model_with_health_awareness(["a", "b"], routing_config=config)

    assert result == "b"


@pytest.mark.asyncio
async def test_health_aware_all_circuit_broken(monkeypatch):
    class _Monitor:
        async def get_load_snapshot(self):
            return {}

        def is_system_overloaded(self, threshold):
            return False

        def get_model_load_score(self, model):
            return 0.0

    class _Router:
        def get_or_create_metrics(self, model):
            metrics = dmr.ModelMetrics(model)
            metrics.consecutive_failures = 3
            return metrics

    monkeypatch.setattr(dmr, "system_load_monitor", _Monitor())
    monkeypatch.setattr(dmr, "get_dynamic_router", lambda: _noop_coro(_Router()))

    config = dmr.RoutingConfig(enable_health_aware_routing=True)
    result = await dmr.get_best_model_with_health_awareness(["a"], routing_config=config)

    assert result == dmr.DEFAULT_FAST_MODEL


@pytest.mark.asyncio
async def test_health_aware_scores_healthy_models(monkeypatch):
    class _Monitor:
        async def get_load_snapshot(self):
            return {}

        def is_system_overloaded(self, threshold):
            return False

        def get_model_load_score(self, model):
            return {"a": 0.9, "b": 0.1}[model]

    class _Router:
        def get_or_create_metrics(self, model):
            metrics = dmr.ModelMetrics(model)
            metrics.record_success(10.0)
            return metrics

    monkeypatch.setattr(dmr, "system_load_monitor", _Monitor())
    monkeypatch.setattr(dmr, "get_dynamic_router", lambda: _noop_coro(_Router()))

    config = dmr.RoutingConfig(enable_health_aware_routing=True)
    result = await dmr.get_best_model_with_health_awareness(["a", "b"], routing_config=config)

    assert result == "b"


# ---------------------------------------------------------------------------
# context/config helpers
# ---------------------------------------------------------------------------

def test_get_context_length_api_key_success(monkeypatch):
    class _Manager:
        def get_context_lengths_by_token(self, token):
            return {"m": 5000}

    monkeypatch.setattr(
        "app.services.apikey_manager.get_apikey_manager", lambda: _Manager()
    )

    assert dmr.get_context_length("m", api_key_token="tok") == 5000


def test_get_context_length_api_key_empty_or_nonpositive(monkeypatch):
    class _Empty:
        def get_context_lengths_by_token(self, token):
            return {}

    monkeypatch.setattr(
        "app.services.apikey_manager.get_apikey_manager", lambda: _Empty()
    )
    monkeypatch.setattr(dmr, "load_agent_model_config", lambda: None)
    monkeypatch.setattr(dmr, "MODEL_CONTEXT_LENGTHS", {"m": 111})

    assert dmr.get_context_length("m", api_key_token="tok") == 111

    class _Zero:
        def get_context_lengths_by_token(self, token):
            return {"m": 0}

    monkeypatch.setattr(
        "app.services.apikey_manager.get_apikey_manager", lambda: _Zero()
    )

    assert dmr.get_context_length("m", api_key_token="tok") == 111


def test_get_context_length_api_key_error_falls_through(monkeypatch):
    def boom():
        raise RuntimeError("no manager")

    monkeypatch.setattr("app.services.apikey_manager.get_apikey_manager", boom)
    monkeypatch.setattr(dmr, "load_agent_model_config", lambda: None)
    monkeypatch.setattr(dmr, "MODEL_CONTEXT_LENGTHS", {"m": 100})

    assert dmr.get_context_length("m", api_key_token="tok") == 100


def test_get_context_length_config_override(monkeypatch):
    monkeypatch.setattr(
        dmr, "load_agent_model_config", lambda: {"model_context_lengths": {"m": 64000}}
    )

    assert dmr.get_context_length("m") == 64000


def test_get_context_length_dynamic_provider(monkeypatch):
    monkeypatch.setattr(
        dmr,
        "load_agent_model_config",
        lambda: {"model_context_lengths": {"m": 0}},
    )
    monkeypatch.setattr(dmr, "MODEL_CONTEXT_LENGTHS", {})

    model = SimpleNamespace(id="m", context_length=12345)
    provider = SimpleNamespace(models=[model])

    class _Manager:
        def get_by_model(self, model_name, user):
            return provider

    monkeypatch.setattr(
        "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager",
        lambda: _Manager(),
    )
    monkeypatch.setattr("app.utils.logging.get_user_id", lambda: "user")

    assert dmr.get_context_length("m") == 12345


def test_get_context_length_dynamic_provider_skips_mismatched_models(monkeypatch):
    monkeypatch.setattr(dmr, "load_agent_model_config", lambda: None)
    monkeypatch.setattr(dmr, "MODEL_CONTEXT_LENGTHS", {})

    other = SimpleNamespace(id="other", context_length=1)
    zero = SimpleNamespace(id="m", context_length=0)
    provider = SimpleNamespace(models=[other, zero])

    class _Manager:
        def get_by_model(self, model_name, user):
            return provider

    monkeypatch.setattr(
        "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager",
        lambda: _Manager(),
    )
    monkeypatch.setattr("app.utils.logging.get_user_id", lambda: None)

    class _CpManager:
        providers = {}

    monkeypatch.setattr(
        "app.services.custom_provider_manager.get_custom_provider_manager",
        lambda: _CpManager(),
    )

    assert dmr.get_context_length("m") == dmr._DEFAULT_CONTEXT_LENGTH


def test_get_context_length_dynamic_provider_no_match(monkeypatch):
    monkeypatch.setattr(dmr, "load_agent_model_config", lambda: None)
    monkeypatch.setattr(dmr, "MODEL_CONTEXT_LENGTHS", {})
    monkeypatch.setattr(
        "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager",
        lambda: SimpleNamespace(get_by_model=lambda m, u: None),
    )

    class _CpManager:
        providers = {}

    monkeypatch.setattr(
        "app.services.custom_provider_manager.get_custom_provider_manager",
        lambda: _CpManager(),
    )

    assert dmr.get_context_length("m") == dmr._DEFAULT_CONTEXT_LENGTH


def test_get_context_length_custom_provider(monkeypatch):
    monkeypatch.setattr(dmr, "load_agent_model_config", lambda: None)
    monkeypatch.setattr(dmr, "MODEL_CONTEXT_LENGTHS", {})

    def boom():
        raise RuntimeError("no dynamic")

    monkeypatch.setattr(
        "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager", boom
    )
    provider = SimpleNamespace(
        enabled=True,
        models=[SimpleNamespace(id="m", context_length=7777)],
    )
    disabled = SimpleNamespace(
        enabled=False,
        models=[SimpleNamespace(id="m", context_length=1)],
    )

    class _CpManager:
        providers = {"p1": provider, "p2": disabled}

    monkeypatch.setattr(
        "app.services.custom_provider_manager.get_custom_provider_manager",
        lambda: _CpManager(),
    )

    assert dmr.get_context_length("m") == 7777


def test_get_context_length_custom_provider_skips_disabled_and_zero(monkeypatch):
    monkeypatch.setattr(dmr, "load_agent_model_config", lambda: None)
    monkeypatch.setattr(dmr, "MODEL_CONTEXT_LENGTHS", {})
    monkeypatch.setattr(
        "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager",
        lambda: SimpleNamespace(get_by_model=lambda m, u: None),
    )
    disabled = SimpleNamespace(
        enabled=False,
        models=[SimpleNamespace(id="m", context_length=999)],
    )
    enabled_zero = SimpleNamespace(
        enabled=True,
        models=[SimpleNamespace(id="other", context_length=10), SimpleNamespace(id="m", context_length=0)],
    )

    class _CpManager:
        providers = {"p1": disabled, "p2": enabled_zero}

    monkeypatch.setattr(
        "app.services.custom_provider_manager.get_custom_provider_manager",
        lambda: _CpManager(),
    )

    assert dmr.get_context_length("m") == dmr._DEFAULT_CONTEXT_LENGTH


def test_get_context_length_custom_provider_error_and_default(monkeypatch):
    monkeypatch.setattr(dmr, "load_agent_model_config", lambda: None)
    monkeypatch.setattr(dmr, "MODEL_CONTEXT_LENGTHS", {})
    monkeypatch.setattr(
        "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager",
        lambda: SimpleNamespace(get_by_model=lambda m, u: None),
    )

    def boom():
        raise RuntimeError("no custom")

    monkeypatch.setattr(
        "app.services.custom_provider_manager.get_custom_provider_manager", boom
    )

    assert dmr.get_context_length("m") == dmr._DEFAULT_CONTEXT_LENGTH


def test_get_max_output_tokens_with_reserve(monkeypatch):
    monkeypatch.setattr(dmr, "get_context_length", lambda model, token=None: 10000)

    assert dmr.get_max_output_tokens("m", reserve_for_input=2000) == 8000
    assert dmr.get_max_output_tokens("m") == 7500
    assert dmr.get_max_output_tokens("m", reserve_for_input=99999) == 1024


@pytest.mark.parametrize(
    ("ctx_len", "expected_min", "expected_max"),
    [(16000, 4096, 8192), (50000, 6144, 12288), (200000, 8192, 16384)],
)
def test_get_model_config_dynamic_tokens(monkeypatch, ctx_len, expected_min, expected_max):
    monkeypatch.setattr(dmr, "get_context_length", lambda model, token=None: ctx_len)
    monkeypatch.setattr(dmr, "load_agent_model_config", lambda: None)
    monkeypatch.setattr(dmr, "MODEL_KEY_TO_ID", {})
    result = dmr.get_model_config("m")

    assert expected_min <= result["max_tokens"] <= expected_max
    assert result["thinking_budget"] >= 2048
    assert result["cost_per_1m_input"] == 0.0


def test_get_model_config_model_override_and_disabled_thinking(monkeypatch):
    monkeypatch.setattr(dmr, "get_context_length", lambda model, token=None: 200000)
    monkeypatch.setattr(
        dmr,
        "load_agent_model_config",
        lambda: {
            "models": {"id": {"temperature": 0.1, "thinking_ratio": 0}},
            "global_thinking_ratio": 0.5,
        },
    )
    monkeypatch.setattr(dmr, "MODEL_KEY_TO_ID", {"Key": "id"})
    monkeypatch.setattr(dmr, "resolve_model_key", lambda m: "Key")

    result = dmr.get_model_config("Key")

    assert result["temperature"] == 0.1
    assert result["thinking_budget"] == 0


def test_get_model_config_cost_from_registry(monkeypatch):
    import app.utils.aicloud.model_registry as registry

    monkeypatch.setattr(dmr, "get_context_length", lambda model, token=None: 16000)
    monkeypatch.setattr(dmr, "load_agent_model_config", lambda: None)
    monkeypatch.setattr(dmr, "MODEL_KEY_TO_ID", {})
    monkeypatch.setitem(
        registry.MODEL_REGISTRY,
        "m",
        SimpleNamespace(cost_per_1m_input=1.5, cost_per_1m_output=2.5),
    )

    result = dmr.get_model_config("m")

    assert result["cost_per_1m_input"] == 1.5
    assert result["cost_per_1m_output"] == 2.5
