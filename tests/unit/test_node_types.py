"""
Node Types 单元测试

测试任务节点基类和各个节点实现
"""

import pytest
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.schema.workflow import TaskType, TaskNode
from app.utils.workflow.node_types.base import TaskNodeBase, NodeResult
from app.utils.workflow.node_types.web_search import WebSearchNode
from app.utils.workflow.node_types.code_execution import CodeExecutionNode
from app.utils.workflow.node_types.chart_generation import ChartGenerationNode


class TestNodeResult:
    """测试 NodeResult 数据类"""

    def test_success_result(self):
        """创建成功结果"""
        result = NodeResult.success_result(data={"key": "value"})
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None

    def test_error_result(self):
        """创建错误结果"""
        result = NodeResult.error_result(error="Something went wrong")
        assert result.success is False
        assert result.data is None
        assert result.error == "Something went wrong"

    def test_result_with_metadata(self):
        """带元数据的结果"""
        result = NodeResult.success_result(
            data="test",
            metadata={"type": "test"}
        )
        assert result.metadata == {"type": "test"}


class TestWebSearchNode:
    """测试 WebSearchNode"""

    def test_validate_params_valid(self):
        """验证有效参数"""
        node = WebSearchNode("test", {"query": "test query"})
        errors = node.validate_params()
        assert len(errors) == 0

    def test_validate_params_missing_query(self):
        """缺少 query 参数"""
        node = WebSearchNode("test", {})
        errors = node.validate_params()
        assert any("query" in e for e in errors)

    def test_validate_params_invalid_count(self):
        """无效的 count 参数"""
        node = WebSearchNode("test", {"query": "test", "count": 100})
        errors = node.validate_params()
        assert any("count" in e for e in errors)

    def test_required_params(self):
        """必需参数列表"""
        node = WebSearchNode("test", {})
        assert "query" in node.get_required_params()

    def test_optional_params(self):
        """可选参数及默认值"""
        node = WebSearchNode("test", {})
        optionals = node.get_optional_params()
        assert optionals["count"] == 5
        assert optionals["lang"] == "zh-CN"

    @pytest.mark.asyncio
    async def test_execute_returns_result(self):
        """执行返回结果"""
        node = WebSearchNode("test", {"query": "test"})
        result = await node.execute({})
        assert isinstance(result, NodeResult)


class TestCodeExecutionNode:
    """测试 CodeExecutionNode"""

    def test_validate_params_valid(self):
        """验证有效参数"""
        node = CodeExecutionNode("test", {"code": "print('hello')"})
        errors = node.validate_params()
        assert len(errors) == 0

    def test_validate_params_missing_code(self):
        """缺少 code 参数"""
        node = CodeExecutionNode("test", {})
        errors = node.validate_params()
        assert any("code" in e for e in errors)

    def test_validate_params_invalid_language(self):
        """无效的 language 参数"""
        node = CodeExecutionNode("test", {"code": "print(1)", "language": "ruby"})
        errors = node.validate_params()
        assert any("language" in e for e in errors)

    def test_validate_params_invalid_timeout(self):
        """无效的 timeout 参数"""
        node = CodeExecutionNode("test", {"code": "print(1)", "timeout": 999})
        errors = node.validate_params()
        assert any("timeout" in e for e in errors)

    def test_required_params(self):
        """必需参数列表"""
        node = CodeExecutionNode("test", {})
        assert "code" in node.get_required_params()

    @pytest.mark.asyncio
    async def test_execute_python_code(self):
        """执行 Python 代码"""
        node = CodeExecutionNode("test", {
            "code": "print('hello')",
            "language": "python"
        })
        result = await node.execute({})
        assert isinstance(result, NodeResult)
        assert result.success is True
        assert "hello" in result.data["stdout"]

    @pytest.mark.asyncio
    async def test_execute_python_with_error(self):
        """执行有错误的 Python 代码"""
        node = CodeExecutionNode("test", {
            "code": "raise ValueError('test error')",
            "language": "python"
        })
        result = await node.execute({})
        assert isinstance(result, NodeResult)

    @pytest.mark.asyncio
    async def test_execute_python_timeout(self):
        """Python 代码超时"""
        node = CodeExecutionNode("test", {
            "code": "import time; time.sleep(10)",
            "language": "python",
            "timeout": 1
        })
        result = await node.execute({})
        assert isinstance(result, NodeResult)
        assert result.success is False
        assert "timeout" in result.error.lower()


class TestChartGenerationNode:
    """测试 ChartGenerationNode"""

    def test_validate_params_valid(self):
        """验证有效参数"""
        node = ChartGenerationNode("test", {
            "chart_type": "bar",
            "title": "Test Chart",
            "data": {"A": 10, "B": 20}
        })
        errors = node.validate_params()
        assert len(errors) == 0

    def test_validate_params_missing_required(self):
        """缺少必需参数"""
        node = ChartGenerationNode("test", {"chart_type": "bar"})
        errors = node.validate_params()
        assert len(errors) >= 2

    def test_validate_params_invalid_chart_type(self):
        """无效的图表类型"""
        node = ChartGenerationNode("test", {
            "chart_type": "invalid",
            "title": "Test",
            "data": {}
        })
        errors = node.validate_params()
        assert any("chart_type" in e for e in errors)

    def test_validate_params_invalid_output_format(self):
        """无效的输出格式"""
        node = ChartGenerationNode("test", {
            "chart_type": "bar",
            "title": "Test",
            "data": {},
            "output_format": "jpg"
        })
        errors = node.validate_params()
        assert any("output_format" in e for e in errors)

    def test_required_params(self):
        """必需参数列表"""
        node = ChartGenerationNode("test", {})
        required = node.get_required_params()
        assert "chart_type" in required
        assert "title" in required
        assert "data" in required

    @pytest.mark.asyncio
    async def test_execute_bar_chart(self):
        """生成柱状图"""
        node = ChartGenerationNode("test", {
            "chart_type": "bar",
            "title": "Test Bar Chart",
            "data": {"A": 10, "B": 20, "C": 15}
        })
        result = await node.execute({})
        assert isinstance(result, NodeResult)

    @pytest.mark.asyncio
    async def test_execute_line_chart(self):
        """生成折线图"""
        node = ChartGenerationNode("test", {
            "chart_type": "line",
            "title": "Test Line Chart",
            "data": [1, 3, 2, 4, 3, 5]
        })
        result = await node.execute({})
        assert isinstance(result, NodeResult)

    @pytest.mark.asyncio
    async def test_execute_pie_chart(self):
        """生成饼图"""
        node = ChartGenerationNode("test", {
            "chart_type": "pie",
            "title": "Test Pie Chart",
            "data": {"A": 30, "B": 50, "C": 20}
        })
        result = await node.execute({})
        assert isinstance(result, NodeResult)


class TestNodeTypeRegistry:
    """测试节点类型注册"""

    def test_websearch_has_correct_type(self):
        """WebSearchNode 类型正确"""
        node = WebSearchNode("test", {"query": "test"})
        assert node.task_type == TaskType.WEB_SEARCH

    def test_code_execution_has_correct_type(self):
        """CodeExecutionNode 类型正确"""
        node = CodeExecutionNode("test", {"code": "print(1)"})
        assert node.task_type == TaskType.CODE_EXECUTION

    def test_chart_generation_has_correct_type(self):
        """ChartGenerationNode 类型正确"""
        node = ChartGenerationNode("test", {
            "chart_type": "bar",
            "title": "Test",
            "data": {}
        })
        assert node.task_type == TaskType.CHART_GENERATION
