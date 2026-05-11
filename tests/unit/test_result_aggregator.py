"""
Result Aggregator 单元测试

测试结果聚合器的功能：
1. 结果记录
2. 上下文构建
3. 上游结果获取
4. 流式输出
5. 结果导出
"""

import pytest
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.schema.workflow import TaskGraph, TaskNode, TaskType, TaskStatus
from app.utils.workflow.node_types.base import NodeResult
from app.utils.workflow.result_aggregator import ResultAggregator


@pytest.fixture
def simple_graph():
    """简单的任务图"""
    return TaskGraph(
        workflow_id="test_workflow",
        nodes=[
            TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={"query": "test"}),
            TaskNode(
                id="node_2",
                type=TaskType.CODE_EXECUTION,
                params={"code": "print(1)"},
                depends_on=["node_1"]
            ),
            TaskNode(
                id="node_3",
                type=TaskType.CHART_GENERATION,
                params={"chart_type": "bar", "title": "Test", "data": {}},
                depends_on=["node_1"]
            ),
            TaskNode(
                id="node_4",
                type=TaskType.FILE_PROCESSING,
                params={},
                depends_on=["node_2", "node_3"]
            ),
        ]
    )


@pytest.fixture
def aggregator(simple_graph):
    """结果聚合器实例"""
    return ResultAggregator("test_workflow", simple_graph)


class TestResultRecording:
    """测试结果记录"""

    def test_record_result(self, aggregator):
        """记录节点结果"""
        result = NodeResult.success_result(data={"key": "value"})
        aggregator.record_result("node_1", result)

        assert aggregator.get_result("node_1") == result
        assert aggregator.get_result("node_1").success is True

    def test_record_multiple_results(self, aggregator):
        """记录多个节点结果"""
        aggregator.record_result("node_1", NodeResult.success_result(data="result_1"))
        aggregator.record_result("node_2", NodeResult.success_result(data="result_2"))

        assert len(aggregator.get_all_results()) == 2

    def test_record_error_result(self, aggregator):
        """记录错误结果"""
        result = NodeResult.error_result(error="Something went wrong")
        aggregator.record_result("node_1", result)

        assert aggregator.get_result("node_1").success is False
        assert aggregator.get_result("node_1").error == "Something went wrong"


class TestContextBuilding:
    """测试上下文构建"""

    def test_context_contains_own_result(self, aggregator):
        """上下文包含自身结果"""
        aggregator.record_result("node_1", NodeResult.success_result(data="my_result"))

        context = aggregator.get_context("node_1")
        assert "node_1_result" in context
        assert context["node_1_result"] == "my_result"

    def test_context_contains_upstream_results(self, aggregator):
        """上下文包含上游结果"""
        aggregator.record_result("node_1", NodeResult.success_result(data="upstream_result"))
        aggregator.record_result("node_2", NodeResult.success_result(data="my_result"))

        context = aggregator.get_context("node_2")
        assert "node_1_result" in context
        assert context["node_1_result"] == "upstream_result"

    def test_context_contains_error_for_failed_upstream(self, aggregator):
        """上下文包含上游错误"""
        aggregator.record_result("node_1", NodeResult.error_result(error="upstream error"))
        aggregator.record_result("node_2", NodeResult.success_result(data=""))

        context = aggregator.get_context("node_2")
        assert "node_1_error" in context
        assert context["node_1_error"] == "upstream error"


class TestUpstreamResults:
    """测试上游结果获取"""

    def test_get_upstream_results(self, aggregator):
        """获取上游结果"""
        aggregator.record_result("node_1", NodeResult.success_result(data="result_1"))

        upstream = aggregator.get_upstream_results("node_2")
        assert "node_1" in upstream
        assert upstream["node_1"].data == "result_1"

    def test_get_upstream_results_none_for_first_node(self, aggregator):
        """首个节点没有上游"""
        upstream = aggregator.get_upstream_results("node_1")
        assert len(upstream) == 0

    def test_get_multiple_upstream_results(self, aggregator):
        """获取多个上游结果"""
        aggregator.record_result("node_2", NodeResult.success_result(data="result_2"))
        aggregator.record_result("node_3", NodeResult.success_result(data="result_3"))

        upstream = aggregator.get_upstream_results("node_4")
        assert "node_2" in upstream
        assert "node_3" in upstream


class TestCompletionTracking:
    """测试完成追踪"""

    def test_is_complete_false(self, aggregator):
        """部分完成时 is_complete 为 False"""
        assert aggregator.is_complete() is False

    def test_is_complete_true(self, simple_graph):
        """全部完成时 is_complete 为 True"""
        agg = ResultAggregator("test", simple_graph)
        agg.record_result("node_1", NodeResult.success_result(data=""))
        agg.record_result("node_2", NodeResult.success_result(data=""))
        agg.record_result("node_3", NodeResult.success_result(data=""))
        agg.record_result("node_4", NodeResult.success_result(data=""))

        assert agg.is_complete() is True

    def test_completion_rate(self, aggregator):
        """完成率计算"""
        assert aggregator.get_completion_rate() == 0.0

        aggregator.record_result("node_1", NodeResult.success_result(data=""))
        assert aggregator.get_completion_rate() == 0.25

        aggregator.record_result("node_2", NodeResult.success_result(data=""))
        assert aggregator.get_completion_rate() == 0.5


class TestSuccessfulFailedResults:
    """测试成功/失败结果分离"""

    def test_get_successful_results(self, aggregator):
        """获取成功结果"""
        aggregator.record_result("node_1", NodeResult.success_result(data=""))
        aggregator.record_result("node_2", NodeResult.error_result(error=""))

        successful = aggregator.get_successful_results()
        assert len(successful) == 1
        assert "node_1" in successful

    def test_get_failed_results(self, aggregator):
        """获取失败结果"""
        aggregator.record_result("node_1", NodeResult.success_result(data=""))
        aggregator.record_result("node_2", NodeResult.error_result(error="failed"))

        failed = aggregator.get_failed_results()
        assert len(failed) == 1
        assert "node_2" in failed


class TestExecutionOrder:
    """测试执行顺序"""

    def test_execution_order(self, aggregator):
        """执行顺序记录"""
        aggregator.record_result("node_1", NodeResult.success_result(data=""))
        aggregator.record_result("node_2", NodeResult.success_result(data=""))

        order = aggregator.get_execution_order()
        assert order == ["node_1", "node_2"]


class TestWorkflowSummary:
    """测试工作流摘要"""

    def test_summary_initial(self, aggregator):
        """初始摘要"""
        summary = aggregator.get_workflow_summary()

        assert summary["workflow_id"] == "test_workflow"
        assert summary["total_nodes"] == 4
        assert summary["completed_nodes"] == 0
        assert summary["pending_nodes"] == 4

    def test_summary_after_completion(self, simple_graph):
        """完成后的摘要"""
        agg = ResultAggregator("test", simple_graph)
        agg.record_result("node_1", NodeResult.success_result(data=""))
        agg.record_result("node_2", NodeResult.success_result(data=""))
        agg.record_result("node_3", NodeResult.success_result(data=""))
        agg.record_result("node_4", NodeResult.error_result(error="failed"))

        summary = agg.get_workflow_summary()

        assert summary["total_nodes"] == 4
        assert summary["completed_nodes"] == 4
        assert summary["successful_nodes"] == 3
        assert summary["failed_nodes"] == 1


class TestExportResults:
    """测试结果导出"""

    def test_export_results(self, aggregator):
        """导出结果"""
        aggregator.record_result("node_1", NodeResult.success_result(data={"key": "value"}))

        exported = aggregator.export_results()

        assert exported["workflow_id"] == "test_workflow"
        assert "task_graph" in exported
        assert "results" in exported
        assert "summary" in exported
        assert "exported_at" in exported

    def test_export_results_structure(self, aggregator):
        """导出结果结构"""
        aggregator.record_result("node_1", NodeResult.success_result(data="test_data"))

        exported = aggregator.export_results()

        assert exported["results"]["node_1"]["success"] is True
        assert exported["results"]["node_1"]["data"] == "test_data"


class TestStreamResults:
    """测试流式输出"""

    @pytest.mark.asyncio
    async def test_stream_results(self, simple_graph):
        """流式输出结果"""
        agg = ResultAggregator("test", simple_graph)
        results = []

        async def collect():
            try:
                async for event in agg.stream_results(interval=0.01):
                    results.append(event)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(collect())

        await asyncio.sleep(0.05)
        agg.record_result("node_1", NodeResult.success_result(data=""))
        agg.record_result("node_2", NodeResult.success_result(data=""))
        agg.record_result("node_3", NodeResult.success_result(data=""))
        agg.record_result("node_4", NodeResult.success_result(data=""))

        await asyncio.sleep(0.1)
        task.cancel()

        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_stream_yields_completion_event(self, simple_graph):
        """流式输出最终完成事件"""
        agg = ResultAggregator("test", simple_graph)

        results = []

        async def collect():
            async for event in agg.stream_results(interval=0.01):
                results.append(event)

        async def complete():
            await asyncio.sleep(0.05)
            agg.record_result("node_1", NodeResult.success_result(data=""))
            agg.record_result("node_2", NodeResult.success_result(data=""))
            agg.record_result("node_3", NodeResult.success_result(data=""))
            agg.record_result("node_4", NodeResult.success_result(data=""))

        await asyncio.gather(collect(), complete())
