"""performance_metrics 回归测试

覆盖已建档缺陷：
- PMC8 orchestrator_testing 调用的 MetricsCollector.get_last_duration 不存在
- PMC2 self.metrics 每个模块的指标点无限增长
"""

import pytest

from app.utils import performance_metrics as pm


def test_get_last_duration_returns_previous_run(tmp_path, monkeypatch):
    """PMC8：get_last_duration 可读，返回指定指标最近一次的耗时。"""
    ticks = iter([100.0, 101.5, 200.0, 200.4])
    monkeypatch.setattr(pm.time, "time", lambda: next(ticks))
    collector = pm.MetricsCollector(storage_path=str(tmp_path))

    assert collector.get_last_duration("TestingMixin", "run_tests") == 0.0

    collector.end_timer(
        "TestingMixin", collector.start_timer("TestingMixin"), "run_tests"
    )
    assert collector.get_last_duration("TestingMixin", "run_tests") == pytest.approx(1500.0)

    collector.end_timer(
        "TestingMixin", collector.start_timer("TestingMixin"), "run_tests"
    )
    assert collector.get_last_duration("TestingMixin", "run_tests") == pytest.approx(400.0)


def test_record_metric_trims_per_module(tmp_path, monkeypatch):
    """PMC2：单模块指标点数量受上限约束，保留最近的记录。"""
    monkeypatch.setattr(pm, "_MAX_METRIC_POINTS_PER_MODULE", 3, raising=False)
    collector = pm.MetricsCollector(storage_path=str(tmp_path))

    for index in range(5):
        collector._record_metric(
            pm.MetricPoint(
                timestamp="t",
                module="M",
                metric_name="run",
                value=float(index),
            )
        )

    points = collector.metrics["M"]
    assert len(points) == 3
    assert [point.value for point in points] == [2.0, 3.0, 4.0]
