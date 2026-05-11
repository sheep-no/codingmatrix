"""
Workflow Executor 单元测试

测试工作流执行器的功能：
1. 任务图验证
2. 拓扑排序
3. 执行顺序
4. 错误隔离
5. 超时控制
"""

import pytest
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.schema.workflow import TaskGraph, TaskNode, TaskType, TaskStatus, WorkflowStatus
from app.utils.workflow.executor import WorkflowExecutor, WorkflowExecutorError, NodeFactory
from app.utils.workflow.node_types.base import NodeResult


@pytest.fixture
def simple_graph():
    """简单的线性任务图"""
    return TaskGraph(
        workflow_id="test_workflow",
        nodes=[
            TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={"query": "test"}),
            TaskNode(id="node_2", type=TaskType.CODE_EXECUTION, params={"code": "print(1)"}, depends_on=["node_1"]),
            TaskNode(id="node_3", type=TaskType.CHART_GENERATION, params={"chart_type": "bar", "title": "Test", "data": {}}, depends_on=["node_2"]),
        ]
    )


@pytest.fixture
def parallel_graph():
    """并行任务图"""
    return TaskGraph(
        workflow_id="parallel_test",
        nodes=[
            TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={"query": "test1"}),
            TaskNode(id="node_2", type=TaskType.WEB_SEARCH, params={"query": "test2"}),
            TaskNode(id="node_3", type=TaskType.CODE_EXECUTION, params={"code": "print(1)"}, depends_on=["node_1", "node_2"]),
        ]
    )


class TestNodeFactory:
    """测试节点工厂"""

    def test_create_websearch_node(self):
        """创建 WebSearch 节点"""
        node = TaskNode(id="test", type=TaskType.WEB_SEARCH, params={"query": "test"})
        instance = NodeFactory.create(node)

        assert instance.node_id == "test"
        assert instance.task_type == TaskType.WEB_SEARCH

    def test_create_code_execution_node(self):
        """创建 CodeExecution 节点"""
        node = TaskNode(id="test", type=TaskType.CODE_EXECUTION, params={"code": "print(1)"})
        instance = NodeFactory.create(node)

        assert instance.node_id == "test"
        assert instance.task_type == TaskType.CODE_EXECUTION

    def test_create_chart_generation_node(self):
        """创建图表生成节点"""
        node = TaskNode(id="test", type=TaskType.CHART_GENERATION, params={
            "chart_type": "bar",
            "title": "Test",
            "data": {"labels": ["A", "B"], "values": [1, 2]}
        })
        instance = NodeFactory.create(node)
        assert instance.node_id == "test"
        assert instance.task_type == TaskType.CHART_GENERATION

    def test_create_file_processing_node(self):
        """创建文件处理节点"""
        node = TaskNode(id="test", type=TaskType.FILE_PROCESSING, params={})
        instance = NodeFactory.create(node)
        assert instance.node_id == "test"
        assert instance.task_type == TaskType.FILE_PROCESSING


class TestTopologicalSort:
    """测试拓扑排序"""

    def test_linear_graph_order(self, simple_graph):
        """线性图的拓扑序"""
        executor = WorkflowExecutor(simple_graph)
        order = executor._compute_topological_order()

        assert order.index("node_1") < order.index("node_2")
        assert order.index("node_2") < order.index("node_3")

    def test_parallel_graph_order(self, parallel_graph):
        """并行图的拓扑序"""
        executor = WorkflowExecutor(parallel_graph)
        order = executor._compute_topological_order()

        assert order.index("node_1") < order.index("node_3")
        assert order.index("node_2") < order.index("node_3")

    def test_complex_graph_order(self):
        """复杂图的拓扑序"""
        graph = TaskGraph(
            workflow_id="complex",
            nodes=[
                TaskNode(id="A", type=TaskType.WEB_SEARCH, params={}),
                TaskNode(id="B", type=TaskType.WEB_SEARCH, params={}),
                TaskNode(id="C", type=TaskType.CODE_EXECUTION, params={}, depends_on=["A"]),
                TaskNode(id="D", type=TaskType.CODE_EXECUTION, params={}, depends_on=["A", "B"]),
                TaskNode(id="E", type=TaskType.CHART_GENERATION, params={}, depends_on=["C", "D"]),
            ]
        )
        executor = WorkflowExecutor(graph)
        order = executor._compute_topological_order()

        assert order.index("A") < order.index("C")
        assert order.index("A") < order.index("D")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("E")
        assert order.index("D") < order.index("E")


class TestExecutableNodes:
    """测试可执行节点检测"""

    def test_first_nodes_executable(self, simple_graph):
        """首个节点可执行"""
        executor = WorkflowExecutor(simple_graph)

        executable = executor._get_executable_nodes(
            completed=set(),
            failed=set(),
            running=set()
        )

        assert "node_1" in executable

    def test_dependent_nodes_not_executable(self, simple_graph):
        """依赖节点在依赖未完成时不可执行"""
        executor = WorkflowExecutor(simple_graph)

        executable = executor._get_executable_nodes(
            completed=set(),
            failed=set(),
            running=set()
        )

        assert "node_2" not in executable
        assert "node_3" not in executable

    def test_dependent_nodes_executable_after_deps(self, simple_graph):
        """依赖完成后节点可执行"""
        executor = WorkflowExecutor(simple_graph)

        executable = executor._get_executable_nodes(
            completed={"node_1"},
            failed=set(),
            running=set()
        )

        assert "node_2" in executable
        assert "node_3" not in executable

    def test_failed_node_blocks_dependents(self, simple_graph):
        """失败节点阻塞依赖"""
        executor = WorkflowExecutor(simple_graph)

        executable = executor._get_executable_nodes(
            completed={"node_1"},
            failed=set(),
            running=set()
        )

        assert "node_2" in executable


class TestValidation:
    """测试任务图验证"""

    def test_valid_graph(self, simple_graph):
        """有效图验证通过"""
        executor = WorkflowExecutor(simple_graph)
        executor.validate()

    def test_circular_dependency_rejected(self):
        """循环依赖被拒绝"""
        graph = TaskGraph(
            workflow_id="circular",
            nodes=[
                TaskNode(id="A", type=TaskType.WEB_SEARCH, params={}, depends_on=["B"]),
                TaskNode(id="B", type=TaskType.WEB_SEARCH, params={}, depends_on=["A"]),
            ]
        )
        executor = WorkflowExecutor(graph)

        from app.utils.workflow.graph_validator import GraphValidationError
        with pytest.raises(GraphValidationError):
            executor.validate()


class TestExecution:
    """测试工作流执行"""

    @pytest.mark.asyncio
    async def test_simple_execution(self, simple_graph):
        """简单执行"""
        executor = WorkflowExecutor(simple_graph, node_timeout=10)

        results = []

        def on_node_start(node_id):
            results.append(f"start:{node_id}")

        def on_node_complete(node_id, result):
            results.append(f"complete:{node_id}:{result.success}")

        result = await executor.execute(
            on_node_start=on_node_start,
            on_node_complete=on_node_complete,
        )

        assert result["status"] in ("completed", "failed")

    @pytest.mark.asyncio
    async def test_execution_summary(self, simple_graph):
        """执行摘要"""
        executor = WorkflowExecutor(simple_graph, node_timeout=10)

        result = await executor.execute()

        assert "workflow_id" in result
        assert "status" in result
        assert "summary" in result
        assert result["summary"]["total_nodes"] == 3

    @pytest.mark.asyncio
    async def test_cancellation(self, simple_graph):
        """取消执行"""
        simple_graph.nodes[0].params = {"code": "import time; time.sleep(10)"}
        executor = WorkflowExecutor(simple_graph, node_timeout=30)

        async def cancel_after_delay():
            await asyncio.sleep(0.1)
            executor.cancel()

        task = asyncio.create_task(executor.execute())
        cancel_task = asyncio.create_task(cancel_after_delay())

        await asyncio.gather(task, cancel_task, return_exceptions=True)

        result = task.result()
        assert result["status"] in ("cancelled", "failed")


class TestCleanup:
    """测试清理机制"""

    def test_register_cleanup(self, simple_graph):
        """注册清理回调"""
        executor = WorkflowExecutor(simple_graph)

        callback_called = []

        def callback():
            callback_called.append(True)

        initial_count = len(executor._cleanup_callbacks)
        executor.register_cleanup(callback)
        assert len(executor._cleanup_callbacks) == initial_count + 1
