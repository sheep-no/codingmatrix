"""orchestrator_progress 缺陷修复回归（OP3 / OP4 / OP6 / OP8）。

OP3: `_pending_tasks` 原为类属性，所有 ProgressMixin 实例共享同一 set；
task 完成回调只 discard、不消费异常。
OP4: `build_progress_event` / `GenerationProgress` 为全库无消费方的死代码。
OP6: `_calculate_changes` 用行数差推算 removed，纯替换场景失真。
OP8: `llm_calls` 原读全库无维护点的 `_llm_call_count`，恒 0。
"""
import asyncio
import json
import time

import pytest

import app.agent.orchestrator_progress as progress_module
from app.agent.orchestrator_progress import CostTracker, ProgressMixin


class _FakeTask:
    """记录 add_done_callback 的假 task。"""

    def __init__(self, exc=None, cancelled=False):
        self.callbacks = []
        self._exc = exc
        self._cancelled = cancelled
        self.exception_retrieved = False

    def add_done_callback(self, cb):
        self.callbacks.append(cb)

    def cancelled(self):
        return self._cancelled

    def exception(self):
        self.exception_retrieved = True
        return self._exc


class _Reporter(ProgressMixin):
    """最小可用的 ProgressMixin 实例。"""

    def __init__(self):
        self.callback = None
        self._start_time = time.time()
        self._current_phase = "test"
        self.generated_files = []


class TestPendingTasksPerInstance:
    def test_pending_tasks_not_a_class_attribute(self):
        assert "_pending_tasks" not in ProgressMixin.__dict__

    @pytest.mark.asyncio
    async def test_instances_do_not_share_task_pool(self):
        async def cb(raw):
            await asyncio.sleep(0)

        a, b = _Reporter(), _Reporter()
        a.callback = cb
        a._report_warning("x")
        assert isinstance(a._pending_tasks, set)
        assert getattr(b, "_pending_tasks", None) is None
        await asyncio.gather(*a._pending_tasks, return_exceptions=True)

    def test_track_task_registers_exception_consuming_callback(self):
        reporter = _Reporter()
        task = _FakeTask()
        reporter._track_task(task)
        assert task in reporter._pending_tasks
        assert task.callbacks == [reporter._on_task_done]

    def test_on_task_done_consumes_exception_and_removes_task(self, monkeypatch):
        logged = []
        monkeypatch.setattr(progress_module.logger, "error", logged.append)
        reporter = _Reporter()
        task = _FakeTask(exc=RuntimeError("boom"))
        reporter._pending_tasks = {task}

        reporter._on_task_done(task)

        assert task.exception_retrieved
        assert reporter._pending_tasks == set()
        assert any("boom" in str(m) for m in logged)

    def test_on_task_done_ignores_cancelled_task(self):
        reporter = _Reporter()
        task = _FakeTask(cancelled=True)
        reporter._pending_tasks = {task}

        reporter._on_task_done(task)

        assert not task.exception_retrieved
        assert reporter._pending_tasks == set()


class TestDeadCodeRemoved:
    def test_build_progress_event_removed(self):
        assert not hasattr(ProgressMixin, "build_progress_event")

    def test_generation_progress_removed(self):
        assert not hasattr(progress_module, "GenerationProgress")


class TestCalculateChanges:
    def test_identical_content(self):
        result = ProgressMixin._calculate_changes("a\nb\nc", "a\nb\nc")
        assert result == {
            "added": 0,
            "removed": 0,
            "modified": 0,
            "total_old": 3,
            "total_new": 3,
        }

    def test_pure_insertion(self):
        result = ProgressMixin._calculate_changes("a\nb", "a\nb\nc")
        assert result["added"] == 1
        assert result["removed"] == 0
        assert result["modified"] == 0

    def test_pure_deletion(self):
        result = ProgressMixin._calculate_changes("a\nb\nc", "a\nb")
        assert result["added"] == 0
        assert result["removed"] == 1
        assert result["modified"] == 0

    def test_full_replacement_reports_both_sides(self):
        old = "\n".join(f"old{i}" for i in range(10))
        new = "\n".join(f"new{i}" for i in range(10))
        result = ProgressMixin._calculate_changes(old, new)
        assert result["added"] == 10
        assert result["removed"] == 10
        assert result["modified"] == 10

    def test_shifted_content_not_counted_as_modified(self):
        result = ProgressMixin._calculate_changes("a\nb\nc", "x\na\nb\nc")
        assert result["added"] == 1
        assert result["removed"] == 0
        assert result["modified"] == 0

    def test_empty_old_content(self):
        result = ProgressMixin._calculate_changes("", "a\nb")
        assert result["added"] == 2
        assert result["removed"] == 0
        assert result["total_old"] == 0
        assert result["total_new"] == 2


class TestLlmCallCount:
    def test_cost_tracker_counts_calls(self):
        tracker = CostTracker()
        tracker.add_usage("m", 10, 20, 0.0)
        tracker.add_usage("m", 10, 20, 0.0)
        assert tracker.llm_calls == 2
        assert tracker.get_summary()["llm_calls"] == 2

    def test_final_metrics_reports_real_call_count(self):
        reporter = _Reporter()
        reporter.cost_tracker = CostTracker()
        reporter.cost_tracker.add_usage("m", 1, 2, 0.0)
        events = []
        reporter.callback = lambda raw: events.append(json.loads(raw))

        metrics = reporter._report_final_metrics()

        assert metrics["llm_calls"] == 1
        assert events[0]["type"] == "performance_metrics"
        assert events[0]["llm_calls"] == 1


class TestEmitEventConvergence:
    """OP5: 所有 `_report_*` 的推送逻辑收敛到 `_emit_event`。"""

    def _spy(self):
        reporter = _Reporter()
        calls = []

        def _emit_event(event, label="事件", callback=None):
            calls.append((event, label, callback))

        reporter._emit_event = _emit_event
        return reporter, calls

    def test_every_report_method_routes_through_emit_event(self):
        reporter, calls = self._spy()

        reporter._report_progress("s", 1, 2)
        reporter._report_file_event("a.py", "x = 1\n", file_type="utils")
        reporter._report_file_diff_event("a.py", "a\n", "b\n")
        reporter._report_model_info("agent", "model")
        reporter._report_done_event({"success": True})
        reporter._report_thinking("agent", "msg")
        reporter._report_test_results({"passed": 1})
        reporter._report_validation_results({"ok": True})
        reporter._report_cost_update({"cost": 1})
        reporter._report_performance_metrics({"x": 1})
        reporter._report_warning("w")
        reporter._report_file_rejected("a.py", "no")
        reporter._report_step_detail("desc")

        assert [call[0]["type"] for call in calls] == [
            "progress",
            "file",
            "file_diff",
            "model_info",
            "done",
            "thinking",
            "test_results",
            "validation_results",
            "cost_update",
            "performance_metrics",
            "warning",
            "file_rejected",
            "step_detail",
        ]
        assert all(call[1] for call in calls)

    def test_report_progress_forwards_explicit_callback_override(self):
        reporter, calls = self._spy()
        explicit = object()

        reporter._report_progress("s", 1, 2, callback=explicit)

        assert calls[0][2] is explicit

    def test_emit_event_prefers_explicit_callback(self):
        reporter = _Reporter()
        seen = []
        default_cb = lambda raw: seen.append(("default", raw))
        override_cb = lambda raw: seen.append(("override", raw))
        reporter.callback = default_cb

        reporter._emit_event({"type": "x"}, callback=override_cb)

        assert len(seen) == 1 and seen[0][0] == "override"

    @pytest.mark.asyncio
    async def test_emit_event_uses_self_callback_and_schedules_coroutine(self):
        reporter = _Reporter()
        seen = []

        async def cb(raw):
            seen.append(json.loads(raw))

        reporter.callback = cb
        reporter._emit_event({"type": "y"})

        assert reporter._pending_tasks
        await asyncio.gather(*reporter._pending_tasks)
        assert seen == [{"type": "y"}]

    def test_emit_event_no_callback_is_noop(self):
        reporter = _Reporter()
        reporter._emit_event({"type": "z"})
        assert getattr(reporter, "_pending_tasks", None) is None
