"""orchestrator_progress 未覆盖分支补测。"""

import json
import time

from app.agent.orchestrator_progress import CostTracker, ProgressMixin


class _Reporter(ProgressMixin):
    def __init__(self, cost_tracker=None):
        self.callback = None
        self.generated_files = []
        if cost_tracker is not None:
            self.cost_tracker = cost_tracker


class _Bare(ProgressMixin):
    pass


def test_update_phase_sets_current_phase():
    reporter = _Reporter()
    reporter._update_phase("generating")
    assert reporter._current_phase == "generating"


def test_track_task_reuses_existing_pool():
    reporter = _Reporter()
    reporter._pending_tasks = set()

    class _Task:
        def add_done_callback(self, cb):
            pass

    task = _Task()
    reporter._track_task(task)
    assert reporter._pending_tasks == {task}


def test_on_task_done_without_pool_is_noop():
    class _Task:
        cancelled = lambda self: False
        exception = lambda self: None

    _Reporter()._on_task_done(_Task())


def test_report_progress_without_start_time_and_out_of_range():
    events = []
    reporter = _Reporter()
    reporter._start_time = 0
    reporter._current_phase = "phase"
    reporter.callback = events.append

    reporter._report_progress("step", 0, 0)
    reporter._report_progress("step", 5, 5)

    assert json.loads(events[0])["percentage"] == 0.0
    assert json.loads(events[1])["percentage"] == 100.0


def test_report_progress_with_start_time_skips_eta_at_final_step():
    events = []
    reporter = _Reporter()
    reporter._start_time = time.time() - 10
    reporter._current_phase = "phase"
    reporter.callback = events.append

    reporter._report_progress("step", 5, 5)

    payload = json.loads(events[0])
    assert payload["elapsed_seconds"] > 0
    assert payload["eta_seconds"] == 0


def test_emit_event_swallows_callback_failure():
    reporter = _Reporter()
    reporter.callback = lambda payload: (_ for _ in ()).throw(RuntimeError("emit boom"))

    reporter._report_warning("warn")


def test_report_current_cost_without_tracker_returns_none():
    assert _Reporter()._report_current_cost() is None


def test_report_current_cost_emits_cost_update():
    events = []
    reporter = _Reporter(cost_tracker=CostTracker())
    reporter.callback = events.append

    summary = reporter._report_current_cost()

    assert summary is not None
    assert json.loads(events[0])["type"] == "cost_update"


def test_report_final_metrics_without_start_time_returns_none():
    assert _Bare()._report_final_metrics() is None


def test_report_final_metrics_without_cost_tracker():
    reporter = _Reporter()
    reporter._start_time = time.time()

    metrics = reporter._report_final_metrics()

    assert metrics["llm_calls"] == 0
    assert "cost" not in metrics


def test_report_final_metrics_includes_counts():
    events = []
    reporter = _Reporter(cost_tracker=CostTracker())
    reporter.callback = events.append
    reporter._start_time = time.time() - 60
    reporter.generated_files = ["a.py", "b.py"]

    metrics = reporter._report_final_metrics()

    assert metrics["files_generated"] == 2
    assert metrics["files_per_minute"] == 2.0
    assert "cost" in metrics
    assert json.loads(events[0])["type"] == "performance_metrics"


def test_estimate_complexity_classifies_file_sizes():
    large = ProgressMixin._estimate_complexity("\n".join(["x = 1"] * 501), "py")
    medium = ProgressMixin._estimate_complexity("\n".join(["x = 1"] * 201), "py")
    small = ProgressMixin._estimate_complexity("\n".join(["x = 1"] * 51), "py")

    assert large["score"] == 3
    assert "large_file" in large["factors"]
    assert medium["score"] == 2
    assert "medium_file" in medium["factors"]
    assert small["score"] == 1
    assert "small_file" in small["factors"]


def test_estimate_complexity_detects_deep_nesting_and_many_definitions():
    content = "\n".join(" " * 20 + "x = 1" for _ in range(60))
    content += "\n" + "\n".join(f"def f{index}():" for index in range(21))

    result = ProgressMixin._estimate_complexity(content, "py")

    assert "deep_nesting" in result["factors"]
    assert "many_definitions" in result["factors"]
    assert "small_file" in result["factors"]
    assert result["level"] == "high"


def test_estimate_complexity_medium_level():
    content = "\n".join("x = 1" for _ in range(501))
    assert ProgressMixin._estimate_complexity(content, "py")["level"] == "medium"


def test_estimate_complexity_with_comments_skips_low_comment_factor():
    content = "\n".join(["# comment"] * 60)
    result = ProgressMixin._estimate_complexity(content, "py")
    assert "low_comments" not in result["factors"]


def test_humanize_size_supports_terabytes():
    assert ProgressMixin._humanize_size(1024**4) == "1.0 TB"
