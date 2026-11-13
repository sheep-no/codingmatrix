"""补测 WorkflowExecutor 的重试、取消、清理与条件跳过分支。"""

import asyncio
from types import SimpleNamespace

import pytest

from app.schema.workflow import RetryConfig, TaskGraph, TaskNode, TaskType, TaskStatus
from app.utils.workflow.executor import WorkflowExecutor, WorkflowExecutorError, NodeFactory
from app.utils.workflow.node_types.base import NodeResult


def _graph(*nodes, workflow_id="wf"):
    return TaskGraph(workflow_id=workflow_id, nodes=list(nodes))


class _RecordingNode:
    """可编程节点替身：按顺序返回预设结果或抛异常。"""

    def __init__(self, node_id, params=None, outcomes=None):
        self.node_id = node_id
        self.params = params or {}
        self.outcomes = list(outcomes or [])
        self.calls = 0
        self.validation_errors = []
        self.approval_callback = None

    def validate_params(self):
        return list(self.validation_errors)

    def set_approval_callback(self, callback):
        self.approval_callback = callback

    async def execute(self, context):
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else NodeResult.success_result(data={})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FactoryPatcher:
    def __init__(self, monkeypatch, mapping):
        self.monkeypatch = monkeypatch
        self.mapping = mapping

    def __enter__(self):
        self.original = NodeFactory.create

        def fake_create(node):
            return self.mapping[node.id]

        self.monkeypatch.setattr(NodeFactory, "create", staticmethod(fake_create))
        return self.mapping

    def __exit__(self, *args):
        return False


class TestNodeFactoryErrors:
    def test_unknown_node_type_raises(self):
        node = SimpleNamespace(type="not-a-type", id="x", params={})
        with pytest.raises(WorkflowExecutorError, match="Unsupported node type"):
            NodeFactory.create(node)


class TestExecuteNodeRetries:
    @pytest.mark.asyncio
    async def test_missing_node_returns_error(self):
        executor = WorkflowExecutor(_graph())
        result = await executor._execute_node("ghost", {}, asyncio.Event())

        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_invalid_params_return_error(self, monkeypatch):
        node = TaskNode(id="n1", type=TaskType.LLM_CALL, params={})
        executor = WorkflowExecutor(_graph(node))
        fake = _RecordingNode("n1")
        fake.validation_errors = ["prompt required"]

        with _FactoryPatcher(monkeypatch, {"n1": fake}):
            result = await executor._execute_node("n1", {}, asyncio.Event())

        assert result.success is False
        assert "prompt required" in result.error

    @pytest.mark.asyncio
    async def test_retry_then_success_uses_backoff(self, monkeypatch):
        node = TaskNode(
            id="n1",
            type=TaskType.LLM_CALL,
            params={},
            retry=RetryConfig(max_retries=2, retry_delay=0.1, backoff_factor=2.0),
        )
        executor = WorkflowExecutor(_graph(node))
        fake = _RecordingNode(
            "n1",
            outcomes=[
                NodeResult.error_result(error="first failure"),
                NodeResult.error_result(error="second failure"),
                NodeResult.success_result(data={"ok": True}),
            ],
        )

        with _FactoryPatcher(monkeypatch, {"n1": fake}):
            result = await executor._execute_node("n1", {}, asyncio.Event())

        assert result.success is True
        assert fake.calls == 3

    @pytest.mark.asyncio
    async def test_timeout_is_retried_then_reported(self, monkeypatch):
        node = TaskNode(
            id="n1",
            type=TaskType.LLM_CALL,
            params={},
            retry=RetryConfig(max_retries=1, retry_delay=0.1, backoff_factor=1.0),
        )
        executor = WorkflowExecutor(_graph(node), node_timeout=0.01)
        fake = _RecordingNode(
            "n1",
            outcomes=[asyncio.TimeoutError(), asyncio.TimeoutError()],
        )

        with _FactoryPatcher(monkeypatch, {"n1": fake}):
            result = await executor._execute_node("n1", {}, asyncio.Event())

        assert result.success is False
        assert "timeout" in result.error.lower()
        assert fake.calls == 2

    @pytest.mark.asyncio
    async def test_generic_exception_is_retried_then_reported(self, monkeypatch):
        node = TaskNode(
            id="n1",
            type=TaskType.LLM_CALL,
            params={},
            retry=RetryConfig(max_retries=1, retry_delay=0.1, backoff_factor=1.0),
        )
        executor = WorkflowExecutor(_graph(node))
        fake = _RecordingNode(
            "n1", outcomes=[RuntimeError("kaput"), RuntimeError("kaput again")]
        )

        with _FactoryPatcher(monkeypatch, {"n1": fake}):
            result = await executor._execute_node("n1", {}, asyncio.Event())

        assert result.success is False
        assert "kaput again" in result.error

    @pytest.mark.asyncio
    async def test_on_failure_skip_returns_success_with_flag(self, monkeypatch):
        node = TaskNode(
            id="n1",
            type=TaskType.LLM_CALL,
            params={},
            retry=None,
            on_failure="skip",
        )
        executor = WorkflowExecutor(_graph(node))
        fake = _RecordingNode("n1", outcomes=[NodeResult.error_result(error="nope")])

        with _FactoryPatcher(monkeypatch, {"n1": fake}):
            result = await executor._execute_node("n1", {}, asyncio.Event())

        assert result.success is True
        assert result.metadata["skipped"] is True

    @pytest.mark.asyncio
    async def test_cancel_event_short_circuits(self, monkeypatch):
        node = TaskNode(id="n1", type=TaskType.LLM_CALL, params={})
        executor = WorkflowExecutor(_graph(node))
        fake = _RecordingNode("n1")
        event = asyncio.Event()
        event.set()

        with _FactoryPatcher(monkeypatch, {"n1": fake}):
            result = await executor._execute_node("n1", {}, event)

        assert result.success is False
        assert "cancelled" in result.error.lower()
        assert fake.calls == 0

    @pytest.mark.asyncio
    async def test_human_approval_callback_is_injected(self, monkeypatch):
        node = TaskNode(id="n1", type=TaskType.HUMAN_APPROVAL, params={})
        callback = lambda *a, **k: True
        executor = WorkflowExecutor(_graph(node), approval_callback=callback)
        fake = _RecordingNode("n1")

        with _FactoryPatcher(monkeypatch, {"n1": fake}):
            await executor._execute_node("n1", {}, asyncio.Event())

        assert fake.approval_callback is callback

    @pytest.mark.asyncio
    async def test_factory_exception_is_wrapped(self, monkeypatch):
        node = TaskNode(id="n1", type=TaskType.LLM_CALL, params={})
        executor = WorkflowExecutor(_graph(node))

        def broken(node):
            raise ValueError("factory boom")

        monkeypatch.setattr(NodeFactory, "create", staticmethod(broken))

        result = await executor._execute_node("n1", {}, asyncio.Event())

        assert result.success is False
        assert "factory boom" in result.error


class TestConditionalSkipHelpers:
    def _conditional_executor(self):
        nodes = [
            TaskNode(
                id="cond",
                type=TaskType.CONDITIONAL,
                params={"true_branch": ["yes"], "false_branch": ["no"]},
            ),
            TaskNode(id="yes", type=TaskType.LLM_CALL, params={}, depends_on=["cond"]),
            TaskNode(id="no", type=TaskType.LLM_CALL, params={}, depends_on=["cond"]),
            TaskNode(id="no_child", type=TaskType.LLM_CALL, params={}, depends_on=["no"]),
        ]
        return WorkflowExecutor(_graph(*nodes))

    def test_select_branch_path_prefers_metadata(self):
        executor = self._conditional_executor()
        result = NodeResult.success_result(
            data={"branch_path": ["from_data"]},
            metadata={"branch_path": ["from_meta"]},
        )

        assert executor._select_branch_path(result) == ["from_meta"]

    def test_select_branch_path_falls_back_to_data(self):
        executor = self._conditional_executor()
        result = NodeResult.success_result(data={"branch_path": ["from_data"]})

        assert executor._select_branch_path(result) == ["from_data"]

    def test_select_branch_path_ignores_non_list(self):
        executor = self._conditional_executor()
        result = NodeResult.success_result(data={"branch_path": "not-a-list"})

        assert executor._select_branch_path(result) is None

    def test_select_branch_path_handles_non_dict_metadata(self):
        executor = self._conditional_executor()
        result = NodeResult(
            success=True,
            data={"branch_path": ["from_data"]},
            metadata=["not-a-dict"],
        )

        assert executor._select_branch_path(result) == ["from_data"]

    def test_apply_conditional_branches_noop_without_branch_path(self):
        executor = self._conditional_executor()
        executor._state_machine = SimpleNamespace()
        executor._aggregator = SimpleNamespace()

        executor._apply_conditional_branches(
            "cond", NodeResult.success_result(data={}), set(), None
        )

    def test_compute_skip_nodes_unknown_conditional_returns_empty(self):
        executor = self._conditional_executor()
        assert executor._compute_skip_nodes("missing", [], set()) == []

    def test_compute_skip_nodes_without_declared_branches_returns_empty(self):
        node = TaskNode(id="cond", type=TaskType.CONDITIONAL, params={})
        executor = WorkflowExecutor(_graph(node))

        assert executor._compute_skip_nodes("cond", [], set()) == []

    def test_compute_skip_nodes_ignores_non_pending_nodes(self):
        from app.utils.workflow.state_machine import WorkflowStateMachine

        executor = self._conditional_executor()
        executor._state_machine = WorkflowStateMachine(
            "wf", executor.task_graph, 60
        )
        executor._state_machine.start_workflow()
        executor._state_machine.start_node("no")
        executor._state_machine.complete_node("no", {})

        skipped = executor._compute_skip_nodes("cond", ["yes"], set())

        assert "no" not in skipped
        # 'no' 已完成，不被记为 skipped，其下游也不再因它被跳过
        assert skipped == []


class TestCancelAndCleanup:
    @pytest.mark.asyncio
    async def test_cancel_marks_event_and_cancels_running_tasks(self):
        executor = WorkflowExecutor(_graph())
        event = asyncio.Event()
        executor._cancel_event = event

        started = asyncio.Event()

        async def forever():
            started.set()
            await asyncio.sleep(10)

        task = asyncio.create_task(forever())
        await started.wait()
        executor._running_tasks["n1"] = task

        executor.cancel()

        assert event.is_set()
        assert task.cancelled() or task.cancelling()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_cancel_skips_finished_tasks(self):
        executor = WorkflowExecutor(_graph())
        event = asyncio.Event()
        executor._cancel_event = event

        async def quick():
            return 1

        task = asyncio.create_task(quick())
        await task
        executor._running_tasks["n1"] = task

        executor.cancel()

        assert task.result() == 1

    @pytest.mark.asyncio
    async def test_cleanup_swallows_callback_errors(self):
        executor = WorkflowExecutor(_graph())
        calls = []

        def broken():
            raise RuntimeError("cleanup boom")

        executor.register_cleanup(lambda: calls.append("ok"))
        executor.register_cleanup(broken)
        executor._running_tasks["n1"] = object()

        await executor._cleanup()

        assert calls == ["ok"]
        assert executor._running_tasks == {}

    @pytest.mark.asyncio
    async def test_workflow_timeout_cancels(self):
        node = TaskNode(id="n1", type=TaskType.LLM_CALL, params={})
        executor = WorkflowExecutor(_graph(node))
        # 构造器把 0 当假值回退默认值，这里直接置零以在首轮循环即判定超时
        executor.timeout = 0

        result = await executor.execute()

        assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_workflow_external_cancel_branch(self, monkeypatch):
        node = TaskNode(id="n1", type=TaskType.LLM_CALL, params={})
        executor = WorkflowExecutor(_graph(node))

        async def cancel_then_slow(self, node_id, context, cancel_event):
            executor.cancel()
            await asyncio.sleep(5)
            return NodeResult.success_result(data={})

        monkeypatch.setattr(WorkflowExecutor, "_execute_node", cancel_then_slow)

        result = await executor.execute()

        assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancelled_task_is_dropped_from_running(self, monkeypatch):
        node = TaskNode(id="n1", type=TaskType.LLM_CALL, params={})
        executor = WorkflowExecutor(_graph(node))

        async def cancel_task(self, node_id, context, cancel_event):
            await asyncio.sleep(0.01)
            executor.cancel()
            await asyncio.sleep(1)
            return NodeResult.success_result(data={})

        monkeypatch.setattr(WorkflowExecutor, "_execute_node", cancel_task)

        result = await executor.execute()

        assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_run_loop_cancelled_error_marks_workflow(self, monkeypatch):
        node = TaskNode(id="n1", type=TaskType.LLM_CALL, params={})
        executor = WorkflowExecutor(_graph(node))

        def raise_cancel(self, completed, failed, running, skipped=None):
            raise asyncio.CancelledError()

        monkeypatch.setattr(WorkflowExecutor, "_get_executable_nodes", raise_cancel)

        result = await executor.execute()

        assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_getters_return_none_before_execution(self):
        executor = WorkflowExecutor(_graph())
        assert executor.get_state_machine() is None
        assert executor.get_aggregator() is None

    def test_max_concurrent_is_capped(self):
        executor = WorkflowExecutor(_graph(), max_concurrent=99)
        assert executor.max_concurrent == WorkflowExecutor.MAX_CONCURRENT_NODES


class TestExecuteLoopBookkeeping:
    @pytest.mark.asyncio
    async def test_failed_node_blocks_dependents_and_fires_callbacks(self, monkeypatch):
        nodes = [
            TaskNode(id="a", type=TaskType.LLM_CALL, params={}),
            TaskNode(id="b", type=TaskType.LLM_CALL, params={}, depends_on=["a"]),
        ]
        executor = WorkflowExecutor(_graph(*nodes))
        completed_events = []
        workflow_events = []

        async def execute_node(self, node_id, context, cancel_event):
            if node_id == "a":
                return NodeResult.error_result(error="a failed")
            return NodeResult.success_result(data={})

        monkeypatch.setattr(WorkflowExecutor, "_execute_node", execute_node)

        result = await executor.execute(
            on_node_complete=lambda nid, res: completed_events.append((nid, res.success)),
            on_workflow_complete=workflow_events.append,
        )

        # 只有 a 被执行，b 因依赖失败而永远不可执行
        assert [nid for nid, _ in completed_events] == ["a"]
        assert workflow_events
        assert result["summary"]["failed_nodes"] == 1

    @pytest.mark.asyncio
    async def test_successful_conditional_applies_skip(self, monkeypatch):
        nodes = [
            TaskNode(
                id="cond",
                type=TaskType.CONDITIONAL,
                params={"true_branch": ["yes"], "false_branch": ["no"]},
            ),
            TaskNode(id="yes", type=TaskType.LLM_CALL, params={}, depends_on=["cond"]),
            TaskNode(id="no", type=TaskType.LLM_CALL, params={}, depends_on=["cond"]),
        ]
        executor = WorkflowExecutor(_graph(*nodes))
        skip_events = []

        async def execute_node(self, node_id, context, cancel_event):
            if node_id == "cond":
                return NodeResult.success_result(
                    data={"branch_path": ["yes"]},
                    metadata={"branch_path": ["yes"]},
                )
            return NodeResult.success_result(data={})

        monkeypatch.setattr(WorkflowExecutor, "_execute_node", execute_node)

        result = await executor.execute(on_node_skip=skip_events.append)

        assert skip_events == ["no"]
        assert result["summary"]["skipped_nodes"] == 1

    def test_cancel_is_noop_without_event(self):
        executor = WorkflowExecutor(_graph())
        executor.cancel()
        assert executor._cancel_event is None

    @pytest.mark.asyncio
    async def test_stuck_graph_without_failed_nodes_breaks(self, monkeypatch):
        node = TaskNode(id="n1", type=TaskType.LLM_CALL, params={})
        executor = WorkflowExecutor(_graph(node))

        monkeypatch.setattr(
            WorkflowExecutor, "_get_executable_nodes", lambda *a, **k: []
        )

        result = await executor.execute()

        assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_cancelled_error_cancels_running_tasks(self, monkeypatch):
        from app.utils.workflow import executor as executor_module

        node = TaskNode(id="n1", type=TaskType.LLM_CALL, params={})
        executor = WorkflowExecutor(_graph(node))

        async def slow(self, node_id, context, cancel_event):
            await asyncio.sleep(5)
            return NodeResult.success_result(data={})

        async def cancelled_wait(*args, **kwargs):
            raise asyncio.CancelledError()

        monkeypatch.setattr(WorkflowExecutor, "_execute_node", slow)
        monkeypatch.setattr(executor_module.asyncio, "wait", cancelled_wait)

        result = await executor.execute()

        assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancelled_error_with_already_completed_state_skips_cancel(self, monkeypatch):
        from app.utils.workflow import executor as executor_module

        node = TaskNode(id="n1", type=TaskType.LLM_CALL, params={})
        executor = WorkflowExecutor(_graph(node))

        async def slow(self, node_id, context, cancel_event):
            await asyncio.sleep(5)
            return NodeResult.success_result(data={})

        async def cancelled_wait(*args, **kwargs):
            executor._state_machine.cancel_workflow("already done")
            raise asyncio.CancelledError()

        monkeypatch.setattr(WorkflowExecutor, "_execute_node", slow)
        monkeypatch.setattr(executor_module.asyncio, "wait", cancelled_wait)

        result = await executor.execute()

        assert result["status"] == "cancelled"
