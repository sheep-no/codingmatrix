"""orchestrator_testing 失败聚类、智能选择与异常回退补测。"""

from pathlib import Path

import pytest

from app.agent.failure_clusterer import FailureCluster
from app.agent.orchestrator_testing import TestingMixin
from app.agent.test_runner import TestResult


class _Runner:
    def __init__(self, result):
        self._result = result

    async def run_tests(self):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _Host(TestingMixin):
    def __init__(self, output_dir=None):
        self.output_dir = output_dir
        self.warnings = []
        self.events = []
        self.progress = []
        self.warning_events = []
        self.phases = []

    def _report_progress(self, *args, **kwargs):
        self.progress.append((args, kwargs))

    def _update_phase(self, *args, **kwargs):
        self.phases.append((args, kwargs))

    def _report_warning(self, **kwargs):
        self.warning_events.append(kwargs)

    def _report_test_results(self, results):
        self.events.append(results)


def _result(**kwargs):
    base = dict(
        success=True,
        total_tests=1,
        passed=1,
        failed=0,
        errors=0,
        logs="",
        failed_tests=[],
    )
    base.update(kwargs)
    return TestResult(**base)


async def test_failed_tests_are_clustered_without_losing_summary():
    logs = "FAILED tests/test_a.py::test_x - ValueError: bad value\nboom\n"
    result = _result(
        success=False,
        total_tests=1,
        passed=0,
        failed=1,
        logs=logs,
        failed_tests=["tests/test_a.py::test_x"],
    )
    host = _Host()

    summary = await host._run_dynamic_tests(_Runner(result))

    assert summary["success"] is False
    assert "failure_clusters" in summary
    cluster = summary["failure_clusters"][0]
    assert cluster["test_count"] == 1
    assert cluster["root_cause"]
    assert cluster["suggested_fix"]
    assert host.warning_events[0]["code"] == "test_failure_cluster"


async def test_failed_tests_without_clusters_still_summarized(monkeypatch):
    result = _result(success=False, passed=0, failed=1, failed_tests=["t"])
    host = _Host()

    async def empty_clusters(*_args, **_kwargs):
        return []

    monkeypatch.setattr(host, "_cluster_test_failures", empty_clusters)

    summary = await host._run_dynamic_tests(_Runner(result))

    assert summary["failure_clusters"] == []
    assert summary["success"] is False


async def test_runner_exception_returns_error_summary():
    host = _Host()

    summary = await host._run_dynamic_tests(_Runner(RuntimeError("runner crashed")))

    assert summary == {"success": False, "message": "runner crashed"}


async def test_select_tests_returns_empty_without_inputs():
    host = _Host()

    assert await host._select_tests(None, None) == []
    assert await host._select_tests(["a.py"], None) == []


async def test_select_tests_uses_analyzer_and_selector(monkeypatch, tmp_path):
    import app.agent.orchestrator_testing as module

    calls = {}

    class _Analyzer:
        def __init__(self, root):
            calls["analyzer_root"] = root

        def analyze(self, modified):
            calls["analyzed"] = modified
            return "changes"

    class _Selector:
        def __init__(self, root):
            calls["selector_root"] = root

        def select_tests(self, changes, profile):
            calls["selected"] = (changes, profile)
            return ["tests/test_a.py"]

    monkeypatch.setattr(module, "ImpactAnalyzer", _Analyzer)
    monkeypatch.setattr(module, "TestSelector", _Selector)

    host = _Host(output_dir=tmp_path)
    test_files = await host._select_tests(["a.py"], object())

    assert test_files == ["tests/test_a.py"]
    assert calls["analyzer_root"] == str(tmp_path)
    assert calls["analyzed"] == ["a.py"]


async def test_select_tests_falls_back_on_error(monkeypatch, tmp_path):
    import app.agent.orchestrator_testing as module

    class _Boom:
        def __init__(self, root):
            raise RuntimeError("no analyzer")

    monkeypatch.setattr(module, "ImpactAnalyzer", _Boom)

    host = _Host(output_dir=tmp_path)
    assert await host._select_tests(["a.py"], object()) == []


async def test_cluster_failures_handles_parametrized_names():
    host = _Host()
    logs = "FAILED tests/test_a.py::test_x[1+2] - ValueError: bad\n"

    clusters = await host._cluster_test_failures(["tests/test_a.py::test_x[1+2]"], logs)

    assert clusters and clusters[0].error_type == "ValueError"


async def test_cluster_failures_handles_single_line_log():
    host = _Host()

    clusters = await host._cluster_test_failures(["test_x"], "FAILED test_x")

    assert len(clusters) == 1


async def test_cluster_failures_returns_empty_on_error(monkeypatch):
    import app.agent.orchestrator_testing as module

    class _Boom:
        def cluster(self, _results):
            raise RuntimeError("cluster failed")

    monkeypatch.setattr(module, "FailureClusterer", _Boom)

    host = _Host()
    assert await host._cluster_test_failures(["t"], "") == []


def test_collect_all_tests_glob(tmp_path):
    (tmp_path / "test_a.py").write_text("", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_b.py").write_text("", encoding="utf-8")

    host = _Host(output_dir=tmp_path)
    collected = host._collect_all_tests()

    assert any(path.endswith("test_a.py") for path in collected)
    assert any(path.endswith("test_b.py") for path in collected)


def test_failure_cluster_exposes_hint_fields():
    cluster = FailureCluster(
        error_type="ValueError",
        error_location="tests/test_a.py:10",
        root_cause_hint="检查输入值",
        count=1,
    )

    assert cluster.root_cause_hint == "检查输入值"
    assert not hasattr(cluster, "suggested_fix")


async def test_successful_run_skips_cluster_and_failure_warning():
    result = _result(success=True, passed=2, total_tests=2, logs="2 passed")
    host = _Host()

    summary = await host._run_dynamic_tests(_Runner(result))

    assert summary["success"] is True
    assert "failure_clusters" not in summary
    assert host.warning_events == []
    assert host.events[0]["success"] is True
