"""性能监控中间件的指标标签必须使用路由模板。

直接使用原始请求路径会把 UUID/数字 ID 带进 Prometheus label，使指标 key
随请求多样性无限增长；未匹配路径则会被任意扫描撑爆基数。
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import prometheus_metrics as metrics_module
from app.utils.performance_monitor import PerformanceMonitorMiddleware


@pytest.fixture
def registry():
    registry = metrics_module.get_prometheus_metrics().get_registry()
    saved_counters = dict(registry._counters)
    saved_histograms = dict(registry._histograms)
    registry._counters.clear()
    registry._histograms.clear()
    yield registry
    registry._counters.clear()
    registry._histograms.clear()
    registry._counters.update(saved_counters)
    registry._histograms.update(saved_histograms)


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(PerformanceMonitorMiddleware)

    @app.get("/items/{item_id}")
    async def get_item(item_id: str):
        return {"id": item_id}

    return TestClient(app)


def _http_request_labels(registry):
    return [
        info["labels"]
        for key, info in registry.get_all()["counters"].items()
        if key.startswith("http_requests_total")
    ]


def test_different_ids_of_same_route_share_one_label(client, registry):
    client.get(f"/items/{uuid.uuid4()}")
    client.get(f"/items/{uuid.uuid4()}")

    assert _http_request_labels(registry) == [
        {"method": "GET", "path": "/items/{item_id}", "status": "200"}
    ]


def test_histogram_keys_also_use_route_template(client, registry):
    client.get(f"/items/{uuid.uuid4()}")
    client.get(f"/items/{uuid.uuid4()}")

    histogram_keys = list(registry._histograms)

    assert len(histogram_keys) == 1
    assert "/items/{item_id}" in histogram_keys[0]
    assert str(uuid.uuid4()) not in histogram_keys[0]


def test_unmatched_paths_collapse_into_single_series(client, registry):
    client.get("/no-such-path-aaa")
    client.get("/no-such-path-bbb")

    assert _http_request_labels(registry) == [
        {"method": "GET", "path": "<unmatched>", "status": "404"}
    ]


def test_metric_path_prefers_route_template():
    scope = {"route": SimpleNamespace(path="/items/{item_id}")}

    assert PerformanceMonitorMiddleware._metric_path(scope) == "/items/{item_id}"


def test_metric_path_falls_back_to_placeholder_when_unmatched():
    assert PerformanceMonitorMiddleware._metric_path({}) == "<unmatched>"
