"""
测试 Prometheus 指标服务
"""
import pytest
from app.services.prometheus_metrics import (
    MetricsRegistry,
    PrometheusMetrics,
    get_prometheus_metrics,
    generate_metrics_text
)


class TestMetricsRegistry:
    """测试指标注册表"""

    def test_counter_increment(self):
        """测试计数器增加"""
        registry = MetricsRegistry()
        registry.counter("test_requests")
        registry.counter("test_requests")
        registry.counter("test_requests")

        data = registry.get_all()
        assert data["counters"]["test_requests"]["value"] == 3

    def test_counter_with_labels(self):
        """测试带标签的计数器"""
        registry = MetricsRegistry()
        registry.counter("http_requests", {"method": "GET", "path": "/api"})
        registry.counter("http_requests", {"method": "POST", "path": "/api"})

        data = registry.get_all()
        assert len(data["counters"]) == 2

    def test_gauge_set(self):
        """测试仪表设置"""
        registry = MetricsRegistry()
        registry.gauge("memory_used", 1024 * 1024 * 100)
        registry.gauge("memory_used", 1024 * 1024 * 200)

        data = registry.get_all()
        assert data["gauges"]["memory_used"]["value"] == 1024 * 1024 * 200

    def test_histogram(self):
        """测试直方图"""
        registry = MetricsRegistry()
        registry.histogram("request_duration", 0.05)
        registry.histogram("request_duration", 0.1)
        registry.histogram("request_duration", 0.3)

        assert "request_duration" in registry._histograms


class TestPrometheusMetrics:
    """测试 Prometheus 指标"""

    def test_singleton(self):
        """测试单例"""
        m1 = get_prometheus_metrics()
        m2 = get_prometheus_metrics()
        assert m1 is m2

    def test_record_request(self):
        """测试记录请求"""
        metrics = get_prometheus_metrics()
        metrics.record_request("GET", "/api/test", 200, 0.05)
        metrics.record_request("POST", "/api/test", 201, 0.1)

    def test_set_websocket_connections(self):
        """测试设置 WebSocket 连接数"""
        metrics = get_prometheus_metrics()
        metrics.set_websocket_connections(10)

    def test_set_memory_usage(self):
        """测试设置内存使用"""
        metrics = get_prometheus_metrics()
        metrics.set_memory_usage(1024 * 1024 * 512)

    def test_set_health_status(self):
        """测试设置健康状态"""
        metrics = get_prometheus_metrics()
        metrics.set_health_status("api", True)
        metrics.set_health_status("database", False)


class TestGenerateMetricsText:
    """测试指标文本生成"""

    def test_generate_metrics_text(self):
        """测试生成 Prometheus 格式文本"""
        metrics = get_prometheus_metrics()
        metrics.record_request("GET", "/api/test", 200, 0.05)
        metrics.set_websocket_connections(5)
        metrics.set_memory_usage(1024 * 1024 * 256)
        metrics.set_health_status("api", True)

        text = generate_metrics_text()
        assert "http_requests_total" in text
        assert "websocket_connections_active" in text
        assert "memory_usage_bytes" in text
        assert "health_status" in text
