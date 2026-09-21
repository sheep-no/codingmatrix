"""收集到的指标必须全部出现在 /metrics 文本中。

原实现只放行 http_requests_total 前缀的 counter，直方图段也从 get_all 起就
丢弃了 histograms，导致 celery_tasks_total、database_connections_active 与
http_request_duration_seconds 收集后静默丢失。
"""

import importlib

import pytest

metrics_module = importlib.import_module("app.services.prometheus_metrics")


@pytest.fixture()
def registry():
    registry = metrics_module.get_prometheus_metrics().get_registry()
    saved = (dict(registry._counters), dict(registry._gauges), dict(registry._histograms))
    registry._counters.clear()
    registry._gauges.clear()
    registry._histograms.clear()
    yield registry
    registry._counters.clear()
    registry._gauges.clear()
    registry._histograms.clear()
    registry._counters.update(saved[0])
    registry._gauges.update(saved[1])
    registry._histograms.update(saved[2])


def test_histogram_is_exported_with_buckets_sum_and_count(registry):
    registry.histogram("http_request_duration_seconds", 0.3, {"method": "GET"})
    registry.histogram("http_request_duration_seconds", 0.7, {"method": "GET"})

    text = metrics_module.generate_metrics_text()

    assert "# TYPE http_request_duration_seconds histogram" in text
    assert 'http_request_duration_seconds_bucket{le="0.5",method="GET"} 1' in text
    assert 'http_request_duration_seconds_bucket{le="+Inf",method="GET"} 2' in text
    assert 'http_request_duration_seconds_sum{method="GET"} 1.0' in text
    assert 'http_request_duration_seconds_count{method="GET"} 2' in text


def test_non_http_counters_are_exported(registry):
    registry.counter("celery_tasks_total", {"task": "cleanup", "status": "success"})
    registry.counter("python_gc_objects_collected", {"generation": "all"})

    text = metrics_module.generate_metrics_text()

    assert "# TYPE celery_tasks_total counter" in text
    assert 'celery_tasks_total{status="success",task="cleanup"} 1' in text
    assert 'python_gc_objects_collected{generation="all"} 1' in text


def test_database_gauges_are_exported(registry):
    registry.gauge("database_connections_active", 2, {"state": "active"})
    registry.gauge("database_connections_active", 5, {"state": "idle"})

    text = metrics_module.generate_metrics_text()

    assert "# TYPE database_connections_active gauge" in text
    assert 'database_connections_active{state="active"} 2' in text
    assert 'database_connections_active{state="idle"} 5' in text
