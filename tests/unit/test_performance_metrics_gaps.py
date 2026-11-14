"""performance_metrics 剩余分支补测。"""

import json

from app.utils import performance_metrics as pm


def test_record_cache_hit_creates_module_bucket(tmp_path):
    collector = pm.MetricsCollector(storage_path=str(tmp_path))

    collector.record_cache_hit("HitOnly")

    metrics = collector.get_module_metrics("HitOnly")
    assert metrics.cache_hits == 1
    assert metrics.cache_hit_rate == 100.0


def test_end_timer_below_threshold_does_not_alert(tmp_path):
    collector = pm.MetricsCollector(storage_path=str(tmp_path))
    collector.end_timer("ImpactAnalyzer", collector.start_timer("ImpactAnalyzer"), "analyze")

    assert collector.get_module_metrics("ImpactAnalyzer").alerts == []


def test_record_test_coverage_creates_module_bucket(tmp_path):
    collector = pm.MetricsCollector(storage_path=str(tmp_path))

    collector.record_test_coverage("LowCoverage", 10.0)

    metrics = collector.get_module_metrics("LowCoverage")
    assert metrics.alerts
    assert "测试覆盖率告警" in metrics.alerts[0]


def test_record_test_coverage_above_threshold_does_not_alert(tmp_path):
    collector = pm.MetricsCollector(storage_path=str(tmp_path))

    collector.record_test_coverage("HighCoverage", 95.0)

    assert collector.get_module_metrics("HighCoverage") is None


def test_record_test_coverage_reuses_existing_bucket(tmp_path):
    collector = pm.MetricsCollector(storage_path=str(tmp_path))
    collector.record_test_coverage("M", 10.0)

    collector.record_test_coverage("M", 20.0)

    assert len(collector.get_module_metrics("M").alerts) == 2


def test_update_cache_hit_rate_ignores_unknown_module_and_zero_total(tmp_path):
    collector = pm.MetricsCollector(storage_path=str(tmp_path))
    collector._update_cache_hit_rate("Missing")

    collector.module_metrics["Empty"] = pm.ModuleMetrics(module_name="Empty")
    collector._update_cache_hit_rate("Empty")

    assert collector.module_metrics["Empty"].cache_hit_rate == 0.0


def test_get_all_metrics_returns_module_map(tmp_path):
    collector = pm.MetricsCollector(storage_path=str(tmp_path))
    collector.record_cache_hit("M")

    assert set(collector.get_all_metrics()) == {"M"}


def test_get_last_duration_returns_zero_when_no_matching_metric(tmp_path):
    collector = pm.MetricsCollector(storage_path=str(tmp_path))
    collector._record_metric(
        pm.MetricPoint(timestamp="t", module="M", metric_name="other", value=5.0)
    )

    assert collector.get_last_duration("M", "execution_time") == 0.0


def test_export_metrics_serializes_infinite_minimum_as_zero(tmp_path):
    collector = pm.MetricsCollector(storage_path=str(tmp_path))
    collector.module_metrics["M"] = pm.ModuleMetrics(module_name="M")

    exported = collector.export_metrics()

    assert exported["M"]["min_time_ms"] == 0
    assert exported["M"]["alerts"] == []


def test_save_metrics_writes_timestamped_file(tmp_path):
    collector = pm.MetricsCollector(storage_path=str(tmp_path))
    collector.record_cache_hit("M")

    collector.save_metrics()

    files = list(tmp_path.glob("metrics_*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["M"]["cache_hits"] == 1


def test_save_metrics_logs_and_swallows_failure(tmp_path, monkeypatch):
    collector = pm.MetricsCollector(storage_path=str(tmp_path))
    errors = []
    monkeypatch.setattr(pm.logger, "error", errors.append)

    def broken_dump(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(json, "dump", broken_dump)

    collector.save_metrics()

    assert errors and "disk full" in errors[0]
