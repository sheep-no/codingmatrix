"""
Workflow 集成测试

测试完整的工作流执行流程：
1. 任务图生成
2. 任务图验证
3. 工作流执行
4. 结果聚合
"""

import pytest
import sys
import os
import asyncio
import json
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.schema.workflow import TaskGraph, TaskNode, TaskType, TaskStatus, WorkflowStatus
from app.utils.workflow.task_decomposer import TaskDecomposer
from app.utils.workflow.graph_validator import GraphValidator
from app.utils.workflow.executor import WorkflowExecutor
from app.utils.workflow.state_machine import WorkflowStateMachine
from app.utils.workflow.result_aggregator import ResultAggregator
from app.utils.workflow.node_types.base import NodeResult


class TestTaskDecomposition:
    """任务分解测试"""

    @pytest.mark.asyncio
    async def test_decompose_with_mock_llm(self):
        """测试使用 Mock LLM 的任务分解"""
        decomposer = TaskDecomposer()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "nodes": [
                {
                    "id": "node_1",
                    "type": "web_search",
                    "params": {"query": "AI news"},
                    "depends_on": []
                },
                {
                    "id": "node_2",
                    "type": "code_execution",
                    "params": {"code": "print('done')"},
                    "depends_on": ["node_1"]
                }
            ]
        })

        with patch('app.utils.workflow.task_decomposer.call_siliconflow', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response
            task_graph = await decomposer.decompose("搜索 AI 新闻并执行代码")

        assert task_graph is not None
        assert len(task_graph.nodes) == 2
        assert task_graph.nodes[0].type == TaskType.WEB_SEARCH
        assert task_graph.nodes[1].type == TaskType.CODE_EXECUTION


class TestGraphValidation:
    """任务图验证测试"""

    def test_valid_graph_passes_validation(self):
        """有效的任务图验证通过"""
        graph = TaskGraph(
            workflow_id="test",
            nodes=[
                TaskNode(id="n1", type=TaskType.WEB_SEARCH, params={}),
                TaskNode(id="n2", type=TaskType.CODE_EXECUTION, params={}, depends_on=["n1"]),
            ]
        )

        validator = GraphValidator()
        is_valid, errors = validator.validate(graph)

        assert is_valid is True
        assert len(errors) == 0

    def test_circular_dependency_detected(self):
        """循环依赖被检测"""
        graph = TaskGraph(
            workflow_id="test",
            nodes=[
                TaskNode(id="n1", type=TaskType.WEB_SEARCH, params={}, depends_on=["n2"]),
                TaskNode(id="n2", type=TaskType.CODE_EXECUTION, params={}, depends_on=["n1"]),
            ]
        )

        validator = GraphValidator()
        is_valid, errors = validator.validate(graph)

        assert is_valid is False
        assert any("Circular dependency" in e for e in errors)


class TestStateMachineLifecycle:
    """状态机生命周期测试"""

    def test_workflow_lifecycle(self):
        """工作流完整生命周期"""
        graph = TaskGraph(
            workflow_id="test",
            nodes=[
                TaskNode(id="n1", type=TaskType.WEB_SEARCH, params={}),
                TaskNode(id="n2", type=TaskType.CODE_EXECUTION, params={}, depends_on=["n1"]),
            ]
        )

        sm = WorkflowStateMachine("test", graph)

        assert sm.get_status() == WorkflowStatus.CREATED

        sm.start_workflow()
        assert sm.get_status() == WorkflowStatus.RUNNING

        sm.start_node("n1")
        sm.complete_node("n1", {"result": "search done"})

        assert sm.get_node_status("n1") == TaskStatus.COMPLETED
        assert sm.is_node_executable("n2") is True

        sm.start_node("n2")
        sm.complete_node("n2", {"result": "code done"})

        assert sm.get_status() == WorkflowStatus.COMPLETED

    def test_workflow_fails_when_node_fails(self):
        """节点失败时工作流失败"""
        graph = TaskGraph(
            workflow_id="test",
            nodes=[
                TaskNode(id="n1", type=TaskType.WEB_SEARCH, params={}),
            ]
        )

        sm = WorkflowStateMachine("test", graph)
        sm.start_workflow()
        sm.start_node("n1")
        sm.fail_node("n1", "Network error")

        assert sm.get_node_status("n1") == TaskStatus.FAILED
        assert sm.is_workflow_complete() is True


class TestResultAggregator:
    """结果聚合器测试"""

    def test_result_recording(self):
        """结果记录"""
        graph = TaskGraph(
            workflow_id="test",
            nodes=[
                TaskNode(id="n1", type=TaskType.WEB_SEARCH, params={}),
            ]
        )

        aggregator = ResultAggregator("test", graph)

        aggregator.record_result("n1", NodeResult.success_result(data={"key": "value"}))

        assert aggregator.get_result("n1") is not None
        assert aggregator.get_result("n1").success is True

    def test_context_building(self):
        """上下文构建"""
        graph = TaskGraph(
            workflow_id="test",
            nodes=[
                TaskNode(id="n1", type=TaskType.WEB_SEARCH, params={}),
                TaskNode(id="n2", type=TaskType.CODE_EXECUTION, params={}, depends_on=["n1"]),
            ]
        )

        aggregator = ResultAggregator("test", graph)
        aggregator.record_result("n1", NodeResult.success_result(data={"results": ["item1", "item2"]}))
        aggregator.record_result("n2", NodeResult.success_result(data={}))

        context = aggregator.get_context("n2")

        assert "n1_result" in context
        assert context["n1_result"]["results"] == ["item1", "item2"]

    def test_completion_tracking(self):
        """完成度追踪"""
        graph = TaskGraph(
            workflow_id="test",
            nodes=[
                TaskNode(id="n1", type=TaskType.WEB_SEARCH, params={}),
                TaskNode(id="n2", type=TaskType.CODE_EXECUTION, params={}),
            ]
        )

        aggregator = ResultAggregator("test", graph)

        assert aggregator.get_completion_rate() == 0.0

        aggregator.record_result("n1", NodeResult.success_result(data={}))

        assert aggregator.get_completion_rate() == 0.5


class TestExecutor:
    """执行器测试"""

    @pytest.mark.asyncio
    async def test_simple_execution(self):
        """简单执行"""
        graph = TaskGraph(
            workflow_id="test",
            nodes=[
                TaskNode(id="n1", type=TaskType.CODE_EXECUTION, params={"code": "print(1)"}),
            ]
        )

        executor = WorkflowExecutor(graph, timeout=60, node_timeout=30)

        result = await executor.execute()

        assert result["workflow_id"] == "test"
        assert result["status"] in ("completed", "failed")

    @pytest.mark.asyncio
    async def test_execution_with_dependencies(self):
        """有依赖的执行"""
        graph = TaskGraph(
            workflow_id="test",
            nodes=[
                TaskNode(id="n1", type=TaskType.CODE_EXECUTION, params={"code": "x = 1"}),
                TaskNode(id="n2", type=TaskType.CODE_EXECUTION, params={"code": "print(x)"}, depends_on=["n1"]),
            ]
        )

        executor = WorkflowExecutor(graph, timeout=60, node_timeout=30)

        result = await executor.execute()

        assert result["workflow_id"] == "test"
        assert result["summary"]["total_nodes"] == 2
