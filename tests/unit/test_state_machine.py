"""
Workflow State Machine 单元测试

测试工作流状态机的功能：
1. 状态初始化
2. 节点状态转换
3. 工作流状态转换
4. 依赖节点执行顺序
5. 超时检测
6. 回调机制
"""

import pytest
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.schema.workflow import TaskGraph, TaskNode, TaskType, TaskStatus, WorkflowStatus
from app.utils.workflow.state_machine import (
    WorkflowStateMachine,
    StateTransitionError,
    NodeState,
)


@pytest.fixture
def simple_graph():
    """简单的任务图"""
    return TaskGraph(
        workflow_id="test_workflow",
        nodes=[
            TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={}),
            TaskNode(id="node_2", type=TaskType.CODE_EXECUTION, params={}, depends_on=["node_1"]),
            TaskNode(id="node_3", type=TaskType.CHART_GENERATION, params={}, depends_on=["node_1"]),
            TaskNode(id="node_4", type=TaskType.FILE_PROCESSING, params={}, depends_on=["node_2", "node_3"]),
        ]
    )


@pytest.fixture
def state_machine(simple_graph):
    """状态机实例"""
    return WorkflowStateMachine("test_workflow", simple_graph, timeout=1800)


class TestStateMachineInitialization:
    """测试状态机初始化"""

    def test_initial_status(self, state_machine):
        """初始状态应该是 CREATED"""
        assert state_machine.get_status() == WorkflowStatus.CREATED

    def test_initial_node_status(self, state_machine):
        """所有节点初始状态应该是 PENDING"""
        for node_id in ["node_1", "node_2", "node_3", "node_4"]:
            assert state_machine.get_node_status(node_id) == TaskStatus.PENDING

    def test_pending_nodes(self, state_machine):
        """get_pending_nodes 返回所有待执行节点"""
        pending = state_machine.get_pending_nodes()
        assert len(pending) == 4
        assert set(pending) == {"node_1", "node_2", "node_3", "node_4"}


class TestWorkflowStart:
    """测试工作流启动"""

    def test_start_workflow(self, state_machine):
        """启动工作流后状态变为 RUNNING"""
        state_machine.start_workflow()
        assert state_machine.get_status() == WorkflowStatus.RUNNING

    def test_start_workflow_twice_raises(self, state_machine):
        """重复启动应该抛出异常"""
        state_machine.start_workflow()
        with pytest.raises(StateTransitionError):
            state_machine.start_workflow()


class TestNodeExecution:
    """测试节点执行"""

    def test_start_node(self, state_machine):
        """启动节点后状态变为 RUNNING"""
        state_machine.start_workflow()
        state_machine.start_node("node_1")
        assert state_machine.get_node_status("node_1") == TaskStatus.RUNNING

    def test_complete_node(self, state_machine):
        """完成节点后状态变为 COMPLETED"""
        state_machine.start_workflow()
        state_machine.start_node("node_1")
        state_machine.complete_node("node_1", result={"data": "test"})
        assert state_machine.get_node_status("node_1") == TaskStatus.COMPLETED

    def test_node_result_stored(self, state_machine):
        """节点结果应该被存储"""
        state_machine.start_workflow()
        state_machine.start_node("node_1")
        result = {"data": "search results"}
        state_machine.complete_node("node_1", result=result)

        node_state = state_machine.get_node_state("node_1")
        assert node_state.result == result

    def test_fail_node(self, state_machine):
        """失败节点状态变为 FAILED"""
        state_machine.start_workflow()
        state_machine.start_node("node_1")
        state_machine.fail_node("node_1", "Execution error")
        assert state_machine.get_node_status("node_1") == TaskStatus.FAILED

    def test_fail_node_stores_error(self, state_machine):
        """失败节点应该存储错误信息"""
        state_machine.start_workflow()
        state_machine.start_node("node_1")
        state_machine.fail_node("node_1", "Network timeout")

        node_state = state_machine.get_node_state("node_1")
        assert node_state.error == "Network timeout"


class TestDependencyEnforcement:
    """测试依赖执行顺序"""

    def test_node_2_not_executable_before_node_1(self, state_machine):
        """node_2 依赖 node_1，node_1 未完成时 node_2 不可执行"""
        state_machine.start_workflow()
        assert state_machine.is_node_executable("node_1") is True
        assert state_machine.is_node_executable("node_2") is False

    def test_node_2_executable_after_node_1_complete(self, state_machine):
        """node_1 完成后 node_2 可执行"""
        state_machine.start_workflow()
        state_machine.start_node("node_1")
        state_machine.complete_node("node_1")
        assert state_machine.is_node_executable("node_2") is True

    def test_node_4_waits_for_dependencies(self, state_machine):
        """node_4 依赖 node_2 和 node_3"""
        state_machine.start_workflow()

        state_machine.start_node("node_1")
        state_machine.complete_node("node_1")

        assert state_machine.is_node_executable("node_4") is False

        state_machine.start_node("node_2")
        state_machine.complete_node("node_2")

        assert state_machine.is_node_executable("node_4") is False

        state_machine.start_node("node_3")
        state_machine.complete_node("node_3")

        assert state_machine.is_node_executable("node_4") is True


class TestWorkflowCompletion:
    """测试工作流完成"""

    def test_workflow_completes_when_all_nodes_done(self, state_machine):
        """所有节点完成后工作流状态变为 COMPLETED"""
        state_machine.start_workflow()

        state_machine.start_node("node_1")
        state_machine.complete_node("node_1")

        state_machine.start_node("node_2")
        state_machine.complete_node("node_2")

        state_machine.start_node("node_3")
        state_machine.complete_node("node_3")

        state_machine.start_node("node_4")
        state_machine.complete_node("node_4")

        assert state_machine.get_status() == WorkflowStatus.COMPLETED

    def test_workflow_fails_when_any_node_fails(self, state_machine):
        """任意节点失败工作流状态变为 FAILED"""
        state_machine.start_workflow()

        state_machine.start_node("node_1")
        state_machine.fail_node("node_1", "Critical error")

        assert state_machine.get_status() == WorkflowStatus.FAILED

    def test_is_workflow_complete(self, state_machine):
        """is_workflow_complete 正确反映完成状态"""
        state_machine.start_workflow()
        assert state_machine.is_workflow_complete() is False

        state_machine.start_node("node_1")
        state_machine.fail_node("node_1", "Error")

        assert state_machine.is_workflow_complete() is True


class TestTimeout:
    """测试超时检测"""

    def test_check_workflow_timeout_not_started(self, state_machine):
        """工作流未启动时不超时"""
        assert state_machine.check_timeout() is False

    def test_timeout_detection(self):
        """超时应该被检测到"""
        graph = TaskGraph(
            workflow_id="timeout_test",
            nodes=[TaskNode(id="n1", type=TaskType.WEB_SEARCH, params={})]
        )
        sm = WorkflowStateMachine("timeout_test", graph, timeout=0)
        sm.start_workflow()

        import time
        time.sleep(0.01)

        assert sm.check_timeout() is True


class TestCallbacks:
    """测试回调机制"""

    def test_callback_registered(self, state_machine):
        """回调应该被正确注册"""
        callback_called = []

        def my_callback(data):
            callback_called.append(data)

        state_machine.register_callback("workflow_started", my_callback)
        state_machine.start_workflow()

        assert len(callback_called) == 1
        assert callback_called[0]["workflow_id"] == "test_workflow"

    def test_multiple_callbacks(self, state_machine):
        """同一个事件可以注册多个回调"""
        calls = []

        state_machine.register_callback("node_completed", lambda d: calls.append(1))
        state_machine.register_callback("node_completed", lambda d: calls.append(2))

        state_machine.start_workflow()
        state_machine.start_node("node_1")
        state_machine.complete_node("node_1")

        assert len(calls) == 2


class TestExecutionSummary:
    """测试执行摘要"""

    def test_execution_summary(self, state_machine):
        """执行摘要包含正确的信息"""
        summary = state_machine.get_execution_summary()

        assert summary["workflow_id"] == "test_workflow"
        assert summary["total_nodes"] == 4
        assert summary["pending"] == 4
        assert summary["completed"] == 0
        assert summary["failed"] == 0

    def test_execution_summary_after_progress(self, state_machine):
        """执行进度反映到摘要中"""
        state_machine.start_workflow()
        state_machine.start_node("node_1")
        state_machine.complete_node("node_1")

        summary = state_machine.get_execution_summary()
        assert summary["pending"] == 3
        assert summary["completed"] == 1


class TestSnapshot:
    """测试状态快照"""

    def test_snapshot_contains_state(self, state_machine):
        """快照包含完整状态"""
        snapshot = state_machine.get_snapshot()

        assert snapshot.workflow_id == "test_workflow"
        assert snapshot.status == WorkflowStatus.CREATED
        assert len(snapshot.nodes) == 4
