"""补齐 WorkflowStateMachine 的边界、卡死检测与回调异常。"""

import time

import pytest

from app.schema.workflow import (
    TaskGraph,
    TaskNode,
    TaskStatus,
    TaskType,
    WorkflowStatus,
)
from app.utils.workflow.state_machine import StateTransitionError, WorkflowStateMachine


def _graph(*nodes):
    return TaskGraph(workflow_id="wf", nodes=list(nodes))


def _sm(timeout=1800, **node_kwargs):
    node = TaskNode(id="n1", type=TaskType.WEB_SEARCH, params={}, **node_kwargs)
    return WorkflowStateMachine("wf", _graph(node), timeout=timeout)


class TestLookups:
    def test_unknown_node_lookups(self):
        sm = _sm()

        assert sm.get_node_status("missing") is None
        assert sm.get_node_state("missing") is None

    def test_is_node_executable_unknown(self):
        assert _sm().is_node_executable("missing") is False

    def test_all_node_states_returns_copy(self):
        sm = _sm()

        states = sm.get_all_node_states()
        states.clear()

        assert sm.get_node_state("n1") is not None

    def test_is_node_executable_rejects_non_pending(self):
        sm = _sm()
        sm.start_workflow()
        sm.start_node("n1")

        assert sm.is_node_executable("n1") is False

    def test_dependency_on_unknown_node_is_ignored(self):
        node = TaskNode(
            id="n1", type=TaskType.WEB_SEARCH, params={}, depends_on=["ghost"]
        )
        sm = WorkflowStateMachine("wf", _graph(node))

        assert sm.is_node_executable("n1") is True

    def test_node_state_without_graph_node_falls_through(self):
        from app.schema.workflow import TaskStatus
        from app.utils.workflow.state_machine import NodeState

        sm = _sm()
        sm._nodes["orphan"] = NodeState(node_id="orphan", status=TaskStatus.PENDING)

        assert sm.is_node_executable("orphan") is True


class TestTransitionGuards:
    def test_start_unknown_node(self):
        with pytest.raises(StateTransitionError, match="Unknown node"):
            _sm().start_node("ghost")

    def test_start_already_running_node(self):
        sm = _sm()
        sm.start_workflow()
        sm.start_node("n1")

        with pytest.raises(StateTransitionError, match="Cannot start"):
            sm.start_node("n1")

    def test_complete_unknown_node(self):
        with pytest.raises(StateTransitionError, match="Unknown node"):
            _sm().complete_node("ghost")

    def test_complete_pending_node(self):
        sm = _sm()

        with pytest.raises(StateTransitionError, match="Cannot complete"):
            sm.complete_node("n1")

    def test_fail_unknown_node(self):
        with pytest.raises(StateTransitionError, match="Unknown node"):
            _sm().fail_node("ghost", "x")

    def test_fail_completed_node(self):
        sm = _sm()
        sm.start_workflow()
        sm.start_node("n1")
        sm.complete_node("n1")

        with pytest.raises(StateTransitionError, match="Cannot fail"):
            sm.fail_node("n1", "late")

    def test_fail_pending_node_allowed(self):
        sm = _sm()
        sm.start_workflow()

        sm.fail_node("n1", "never ran")

        assert sm.get_node_status("n1") == TaskStatus.FAILED

    def test_fail_before_workflow_start_skips_stuck_check(self):
        sm = _sm()

        sm.fail_node("n1", "pre-start")

        assert sm.get_status() == WorkflowStatus.CREATED

    def test_skip_unknown_node(self):
        with pytest.raises(StateTransitionError, match="Unknown node"):
            _sm().skip_node("ghost")

    def test_skip_running_node(self):
        sm = _sm()
        sm.start_workflow()
        sm.start_node("n1")

        with pytest.raises(StateTransitionError, match="Cannot skip"):
            sm.skip_node("n1")

    def test_skip_pending_node_marks_skipped(self):
        sm = _sm()
        sm.start_workflow()

        sm.skip_node("n1", "branch not taken")

        assert sm.get_node_status("n1") == TaskStatus.SKIPPED
        assert sm.get_node_state("n1").error == "branch not taken"

    def test_skip_before_workflow_start_skips_completion_check(self):
        sm = _sm()

        sm.skip_node("n1")

        assert sm.get_status() == WorkflowStatus.CREATED


class TestStuckWorkflow:
    def test_failed_node_with_running_peer_is_not_stuck(self):
        graph = _graph(
            TaskNode(id="a", type=TaskType.WEB_SEARCH, params={}),
            TaskNode(id="b", type=TaskType.WEB_SEARCH, params={}),
            TaskNode(id="c", type=TaskType.WEB_SEARCH, params={}, depends_on=["a"]),
        )
        sm = WorkflowStateMachine("wf", graph)
        sm.start_workflow()
        sm.start_node("b")
        sm.start_node("a")
        sm.fail_node("a", "boom")

        assert sm.get_status() == WorkflowStatus.RUNNING

        sm.complete_node("b")

        assert sm.get_status() == WorkflowStatus.FAILED

    def test_failed_node_blocking_all_paths_marks_stuck(self):
        graph = _graph(
            TaskNode(id="a", type=TaskType.WEB_SEARCH, params={}),
            TaskNode(id="b", type=TaskType.WEB_SEARCH, params={}, depends_on=["a"]),
        )
        sm = WorkflowStateMachine("wf", graph)
        sm.start_workflow()
        sm.start_node("a")
        sm.fail_node("a", "boom")

        assert sm.get_status() == WorkflowStatus.FAILED
        assert "stuck" in sm._error.lower()

    def test_no_failed_nodes_is_not_stuck(self):
        sm = _sm()
        sm.start_workflow()
        sm.start_node("n1")
        sm.complete_node("n1")

        assert sm.get_status() == WorkflowStatus.COMPLETED

    def test_all_nodes_done_with_failure_emits_failure(self):
        graph = _graph(
            TaskNode(id="a", type=TaskType.WEB_SEARCH, params={}),
            TaskNode(id="b", type=TaskType.WEB_SEARCH, params={}),
        )
        sm = WorkflowStateMachine("wf", graph)
        events = []
        sm.register_callback("workflow_failed", events.append)
        sm.start_workflow()
        sm.start_node("a")
        sm.fail_node("a", "boom")
        sm.start_node("b")
        sm.complete_node("b")

        assert sm.get_status() == WorkflowStatus.FAILED
        assert events and events[0]["failed_nodes"] == ["a"]


class TestCancel:
    def test_cancel_running_workflow(self):
        sm = _sm()
        sm.start_workflow()
        sm.start_node("n1")

        sm.cancel_workflow("user aborted")

        assert sm.get_status() == WorkflowStatus.CANCELLED
        assert sm.get_node_status("n1") == TaskStatus.FAILED
        assert sm.get_node_state("n1").error == "Cancelled: user aborted"
        assert sm.is_workflow_complete() is True

    def test_cancel_leaves_finished_nodes_untouched(self):
        graph = _graph(
            TaskNode(id="a", type=TaskType.WEB_SEARCH, params={}),
            TaskNode(id="b", type=TaskType.WEB_SEARCH, params={}),
        )
        sm = WorkflowStateMachine("wf", graph)
        sm.start_workflow()
        sm.start_node("a")
        sm.complete_node("a")

        sm.cancel_workflow("stop")

        assert sm.get_node_status("a") == TaskStatus.COMPLETED
        assert sm.get_node_status("b") == TaskStatus.FAILED

    def test_cancel_without_reason(self):
        sm = _sm()
        sm.start_workflow()

        sm.cancel_workflow()

        assert sm.get_node_state("n1").error == "Cancelled: User cancelled"

    def test_cancel_completed_raises(self):
        sm = _sm()
        sm.start_workflow()
        sm.start_node("n1")
        sm.complete_node("n1")

        with pytest.raises(StateTransitionError, match="Cannot cancel"):
            sm.cancel_workflow()


class TestNodeTimeout:
    def test_unknown_node(self):
        assert _sm().check_node_timeout("ghost") is False

    def test_not_started(self):
        assert _sm().check_node_timeout("n1") is False

    def test_not_exceeded(self):
        sm = _sm()
        sm.start_workflow()
        sm.start_node("n1")

        assert sm.check_node_timeout("n1", node_timeout=300) is False

    def test_exceeded(self):
        sm = _sm()
        sm.start_workflow()
        sm.start_node("n1")
        sm.get_node_state("n1").started_at = sm._nodes["n1"].started_at - __import__(
            "datetime"
        ).timedelta(seconds=10)

        assert sm.check_node_timeout("n1", node_timeout=5) is True

    def test_workflow_timeout_not_exceeded(self):
        sm = _sm(timeout=1800)
        sm.start_workflow()

        assert sm.check_timeout() is False


class TestCallbacks:
    def test_callback_exception_is_logged(self, monkeypatch):
        from app.utils.workflow import state_machine as module

        errors = []
        monkeypatch.setattr(module.logger, "error", lambda *a, **k: errors.append(a))
        sm = _sm()

        def boom(_data):
            raise RuntimeError("callback failed")

        sm.register_callback("workflow_started", boom)
        sm.start_workflow()

        assert errors

    def test_unregistered_event_does_nothing(self):
        sm = _sm()

        sm._emit_event("unknown_event", {})

        assert sm.get_status() == WorkflowStatus.CREATED


class TestSummary:
    def test_summary_before_start(self):
        summary = _sm().get_execution_summary()

        assert summary["started_at"] is None
        assert summary["completed_at"] is None
        assert summary["skipped"] == 0

    def test_summary_after_skip(self):
        sm = _sm()
        sm.start_workflow()
        sm.skip_node("n1")

        summary = sm.get_execution_summary()

        assert summary["skipped"] == 1
        assert summary["status"] == WorkflowStatus.COMPLETED.value
