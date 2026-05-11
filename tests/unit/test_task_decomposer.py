"""
Task Decomposer 单元测试

测试任务分解器的功能：
1. 提示词构建
2. LLM 响应解析
3. 结果验证
"""

import pytest
import sys
import os
import json
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.schema.workflow import TaskGraph, TaskNode, TaskType
from app.utils.workflow.task_decomposer import (
    TaskDecomposer,
    TaskDecomposerError,
    decompose_request,
)


class TestPromptBuilding:
    """测试提示词构建"""

    def test_build_prompt(self):
        """构建提示词"""
        decomposer = TaskDecomposer()
        prompt = decomposer._build_prompt("帮我搜索 AI 新闻")

        assert "你是一个任务规划专家" in prompt
        assert "帮我搜索 AI 新闻" in prompt
        assert "web_search" in prompt
        assert "code_execution" in prompt

    def test_prompt_includes_node_types(self):
        """提示词包含所有节点类型"""
        decomposer = TaskDecomposer()
        prompt = decomposer._build_prompt("测试请求")

        assert "web_search" in prompt
        assert "code_execution" in prompt
        assert "chart_generation" in prompt
        assert "file_processing" in prompt


class TestResponseParsing:
    """测试响应解析"""

    def test_parse_valid_json_response(self):
        """解析有效的 JSON 响应"""
        decomposer = TaskDecomposer()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "nodes": [
                {
                    "id": "node_1",
                    "type": "web_search",
                    "params": {"query": "AI news", "count": 5},
                    "depends_on": []
                },
                {
                    "id": "node_2",
                    "type": "code_execution",
                    "params": {"code": "print('hello')"},
                    "depends_on": ["node_1"]
                }
            ]
        })

        task_graph = decomposer._parse_response(mock_response, "测试请求")

        assert len(task_graph.nodes) == 2
        assert task_graph.nodes[0].id == "node_1"
        assert task_graph.nodes[0].type == TaskType.WEB_SEARCH
        assert task_graph.nodes[1].id == "node_2"
        assert task_graph.nodes[1].type == TaskType.CODE_EXECUTION
        assert "node_1" in task_graph.nodes[1].depends_on

    def test_parse_json_with_fenced_code(self):
        """解析带代码块的 JSON"""
        decomposer = TaskDecomposer()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """```json
{
  "nodes": [
    {
      "id": "node_1",
      "type": "web_search",
      "params": {"query": "test"},
      "depends_on": []
    }
  ]
}
```"""

        task_graph = decomposer._parse_response(mock_response, "测试")

        assert len(task_graph.nodes) == 1
        assert task_graph.nodes[0].type == TaskType.WEB_SEARCH

    def test_parse_ignores_unknown_types(self):
        """解析时忽略未知类型"""
        decomposer = TaskDecomposer()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "nodes": [
                {
                    "id": "node_1",
                    "type": "web_search",
                    "params": {},
                    "depends_on": []
                },
                {
                    "id": "node_2",
                    "type": "unknown_type",
                    "params": {},
                    "depends_on": []
                }
            ]
        })

        task_graph = decomposer._parse_response(mock_response, "测试")

        assert len(task_graph.nodes) == 1
        assert task_graph.nodes[0].type == TaskType.WEB_SEARCH

    def test_auto_generate_node_id(self):
        """自动生成节点 ID"""
        decomposer = TaskDecomposer()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "nodes": [
                {
                    "type": "web_search",
                    "params": {},
                    "depends_on": []
                }
            ]
        })

        task_graph = decomposer._parse_response(mock_response, "测试")

        assert len(task_graph.nodes) == 1
        assert task_graph.nodes[0].id == "node_1"


class TestResultValidation:
    """测试结果验证"""

    def test_validate_empty_graph(self):
        """验证空图"""
        decomposer = TaskDecomposer()
        graph = TaskGraph(workflow_id="test", nodes=[])

        errors = decomposer.validate_result(graph)

        assert len(errors) > 0
        assert any("没有节点" in e for e in errors)

    def test_validate_valid_graph(self):
        """验证有效图"""
        decomposer = TaskDecomposer()
        graph = TaskGraph(
            workflow_id="test",
            nodes=[
                TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={}),
                TaskNode(id="node_2", type=TaskType.CODE_EXECUTION, params={}, depends_on=["node_1"]),
            ]
        )

        errors = decomposer.validate_result(graph)

        assert len(errors) == 0

    def test_validate_duplicate_node_ids(self):
        """验证重复节点 ID"""
        decomposer = TaskDecomposer()
        graph = TaskGraph(
            workflow_id="test",
            nodes=[
                TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={}),
                TaskNode(id="node_1", type=TaskType.CODE_EXECUTION, params={}),
            ]
        )

        errors = decomposer.validate_result(graph)

        assert len(errors) > 0
        assert any("重复" in e for e in errors)

    def test_validate_missing_dependency(self):
        """验证缺失的依赖"""
        decomposer = TaskDecomposer()
        graph = TaskGraph(
            workflow_id="test",
            nodes=[
                TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={}),
                TaskNode(id="node_2", type=TaskType.CODE_EXECUTION, params={}, depends_on=["node_999"]),
            ]
        )

        errors = decomposer.validate_result(graph)

        assert len(errors) > 0
        assert any("node_999" in e for e in errors)


class TestTaskDecomposerError:
    """测试异常处理"""

    def test_invalid_json_raises_error(self):
        """无效 JSON 抛出异常"""
        decomposer = TaskDecomposer()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "这不是 JSON"

        with pytest.raises(TaskDecomposerError) as exc_info:
            decomposer._parse_response(mock_response, "测试")

        assert "无法解析" in str(exc_info.value)


class TestWorkflowId:
    """测试工作流 ID 生成"""

    def test_workflow_id_format(self):
        """工作流 ID 格式"""
        decomposer = TaskDecomposer()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "nodes": [
                {"id": "node_1", "type": "web_search", "params": {}, "depends_on": []}
            ]
        })

        task_graph = decomposer._parse_response(mock_response, "测试")

        assert task_graph.workflow_id.startswith("wf_")
        assert len(task_graph.workflow_id) == 11  # wf_ + 8 hex chars
