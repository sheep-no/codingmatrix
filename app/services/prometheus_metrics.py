"""
Prometheus 指标服务

轻量级指标暴露，不依赖额外的 Prometheus 库
"""
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class Counter:
    """计数器"""
    value: float = 0
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class Gauge:
    """仪表"""
    value: float = 0
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class HistogramBucket:
    """直方图桶"""
    le: float
    count: float = 0


class MetricsRegistry:
    """
    指标注册表

    线程安全，支持 Counter、Gauge、Histogram
    """

    def __init__(self):
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, List[HistogramBucket]] = {}
        self._lock = threading.RLock()

        self._histogram_buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

    def counter(self, name: str, labels: Dict[str, str] = None) -> float:
        """增加计数器"""
        with self._lock:
            key = self._make_key(name, labels)
            if key not in self._counters:
                self._counters[key] = Counter(value=0, labels=labels or {})
            self._counters[key].value += 1
            return self._counters[key].value

    def gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """设置仪表值"""
        with self._lock:
            key = self._make_key(name, labels)
            self._gauges[key] = Gauge(value=value, labels=labels or {})

    def histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        """记录直方图值"""
        with self._lock:
            key = self._make_key(name, labels)
            if key not in self._histograms:
                self._histograms[key] = [
                    HistogramBucket(le=le) for le in self._histogram_buckets
                ]

            for bucket in self._histograms[key]:
                if value <= bucket.le:
                    bucket.count += 1

    def get_all(self) -> Dict:
        """获取所有指标"""
        with self._lock:
            return {
                "counters": {k: {"value": v.value, "labels": v.labels}
                            for k, v in self._counters.items()},
                "gauges": {k: {"value": v.value, "labels": v.labels}
                          for k, v in self._gauges.items()},
            }

    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """生成指标键"""
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"


_metrics_registry = MetricsRegistry()


class PrometheusMetrics:
    """
    Prometheus 指标收集器

    提供业务指标收集功能
    """

    def __init__(self):
        self._registry = _metrics_registry
        self._request_counts: Dict[str, int] = {}
        self._request_durations: List[float] = []
        self._lock = threading.RLock()

    def record_request(self, method: str, path: str, status: int, duration: float):
        """记录 HTTP 请求"""
        labels = {
            "method": method,
            "path": path,
            "status": str(status)
        }
        self._registry.counter("http_requests_total", labels)
        self._registry.histogram("http_request_duration_seconds", duration, labels)

    def set_websocket_connections(self, count: int):
        """设置 WebSocket 连接数"""
        self._registry.gauge("websocket_connections_active", count)

    def set_database_connections(self, active: int, idle: int):
        """设置数据库连接数"""
        self._registry.gauge("database_connections_active", active, {"state": "active"})
        self._registry.gauge("database_connections_active", idle, {"state": "idle"})

    def record_celery_task(self, task_name: str, status: str):
        """记录 Celery 任务"""
        labels = {"task": task_name, "status": status}
        self._registry.counter("celery_tasks_total", labels)

    def set_memory_usage(self, bytes_used: int):
        """设置内存使用"""
        self._registry.gauge("memory_usage_bytes", bytes_used)

    def set_health_status(self, component: str, status: bool):
        """设置组件健康状态"""
        self._registry.gauge("health_status", 1 if status else 0, {"component": component})

    def get_registry(self) -> MetricsRegistry:
        return self._registry


_prometheus_metrics: Optional[PrometheusMetrics] = None


def get_prometheus_metrics() -> PrometheusMetrics:
    """获取指标收集器单例"""
    global _prometheus_metrics
    if _prometheus_metrics is None:
        _prometheus_metrics = PrometheusMetrics()
    return _prometheus_metrics


def generate_metrics_text() -> str:
    """生成 Prometheus 格式的指标文本"""
    registry = get_prometheus_metrics().get_registry()
    data = registry.get_all()

    lines = []

    lines.append("# HELP http_requests_total Total HTTP requests")
    lines.append("# TYPE http_requests_total counter")
    for key, info in data["counters"].items():
        if key.startswith("http_requests_total"):
            labels_str = _format_labels(info["labels"])
            lines.append(f'{key}{labels_str} {info["value"]}')

    lines.append("")
    lines.append("# HELP http_request_duration_seconds HTTP request duration")
    lines.append("# TYPE http_request_duration_seconds histogram")

    lines.append("")
    lines.append("# HELP websocket_connections_active WebSocket connections")
    lines.append("# TYPE websocket_connections_active gauge")
    for key, info in data["gauges"].items():
        if "websocket" in key:
            labels_str = _format_labels(info["labels"])
            lines.append(f'{key.split("{")[0]}{labels_str} {info["value"]}')

    lines.append("")
    lines.append("# HELP health_status Component health status")
    lines.append("# TYPE health_status gauge")
    for key, info in data["gauges"].items():
        if "health" in key:
            labels_str = _format_labels(info["labels"])
            lines.append(f'{key.split("{")[0]}{labels_str} {info["value"]}')

    lines.append("")
    lines.append("# HELP memory_usage_bytes Memory usage in bytes")
    lines.append("# TYPE memory_usage_bytes gauge")
    for key, info in data["gauges"].items():
        if "memory" in key:
            labels_str = _format_labels(info["labels"])
            lines.append(f'{key.split("{")[0]}{labels_str} {info["value"]}')

    return "\n".join(lines)


def _format_labels(labels: Dict[str, str]) -> str:
    """格式化标签"""
    if not labels:
        return ""
    label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{{{label_str}}}"


prometheus_metrics = get_prometheus_metrics()
