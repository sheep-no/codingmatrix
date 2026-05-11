"""
Graph Validator 单元测试

测试任务图验证器的功能：
1. 节点 ID 唯一性检测
2. 依赖节点存在性检测
3. 任务类型有效性检测
4. 循环依赖检测（Kahn 算法）
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.schema.workflow import TaskGraph, TaskNode, TaskType
from app.utils.workflow.graph_validator import (
    GraphValidator,
    GraphValidationError,
    validate_task_graph,
    validate_task_graph_or_raise,
)


class TestNodeIdUniqueness:
    """测试节点 ID 唯一性"""

    def test_valid_unique_ids(self):
        """唯一节点 ID 应该通过"""
        graph = TaskGraph(
            workflow_id="test_1",
            nodes=[
                TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={}),
                TaskNode(id="node_2", type=TaskType.CODE_EXECUTION, params={}),
            ]
        )
        validator = GraphValidator()
        is_valid, errors = validator.validate(graph)
        assert is_valid is True
        assert len(errors) == 0

    def test_duplicate_ids(self):
        """重复节点 ID 应该失败"""
        graph = TaskGraph(
            workflow_id="test_2",
            nodes=[
                TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={}),
                TaskNode(id="node_1", type=TaskType.CODE_EXECUTION, params={}),
            ]
        )
        validator = GraphValidator()
        is_valid, errors = validator.validate(graph)
        assert is_valid is False
        assert any("Duplicate node ID" in err for err in errors)


class TestDependencyExistence:
    """测试依赖节点存在性"""

    def test_valid_dependency(self):
        """有效的依赖引用应该通过"""
        graph = TaskGraph(
            workflow_id="test_3",
            nodes=[
                TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={}),
                TaskNode(id="node_2", type=TaskType.CODE_EXECUTION, params={}, depends_on=["node_1"]),
            ]
        )
        validator = GraphValidator()
        is_valid, errors = validator.validate(graph)
        assert is_valid is True

    def test_missing_dependency(self):
        """引用不存在的节点应该失败"""
        graph = TaskGraph(
            workflow_id="test_4",
            nodes=[
                TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={}),
                TaskNode(id="node_2", type=TaskType.CODE_EXECUTION, params={}, depends_on=["node_999"]),
            ]
        )
        validator = GraphValidator()
        is_valid, errors = validator.validate(graph)
        assert is_valid is False
        assert any("non-existent node" in err for err in errors)


class TestTaskTypeValidity:
    """测试任务类型有效性"""

    def test_valid_task_types(self):
        """所有有效任务类型应该通过"""
        for task_type in TaskType:
            graph = TaskGraph(
                workflow_id=f"test_{task_type.value}",
                nodes=[TaskNode(id="node_1", type=task_type, params={})]
            )
            validator = GraphValidator()
            is_valid, errors = validator.validate(graph)
            assert is_valid is True, f"TaskType {task_type} should be valid"


class TestCircularDependency:
    """测试循环依赖检测"""

    def test_no_circular_dependency(self):
        """无循环依赖应该通过"""
        graph = TaskGraph(
            workflow_id="test_5",
            nodes=[
                TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={}),
                TaskNode(id="node_2", type=TaskType.CODE_EXECUTION, params={}, depends_on=["node_1"]),
                TaskNode(id="node_3", type=TaskType.CHART_GENERATION, params={}, depends_on=["node_1", "node_2"]),
            ]
        )
        validator = GraphValidator()
        is_valid, errors = validator.validate(graph)
        assert is_valid is True

    def test_simple_circular_dependency(self):
        """简单循环依赖应该被检测到"""
        graph = TaskGraph(
            workflow_id="test_6",
            nodes=[
                TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={}, depends_on=["node_2"]),
                TaskNode(id="node_2", type=TaskType.CODE_EXECUTION, params={}, depends_on=["node_1"]),
            ]
        )
        validator = GraphValidator()
        is_valid, errors = validator.validate(graph)
        assert is_valid is False
        assert any("Circular dependency" in err for err in errors)

    def test_complex_circular_dependency(self):
        """复杂循环依赖应该被检测到: A->B->C->D->A"""
        graph = TaskGraph(
            workflow_id="test_7",
            nodes=[
                TaskNode(id="A", type=TaskType.WEB_SEARCH, params={}, depends_on=["D"]),
                TaskNode(id="B", type=TaskType.WEB_SEARCH, params={}, depends_on=["A"]),
                TaskNode(id="C", type=TaskType.WEB_SEARCH, params={}, depends_on=["B"]),
                TaskNode(id="D", type=TaskType.WEB_SEARCH, params={}, depends_on=["C"]),
            ]
        )
        validator = GraphValidator()
        is_valid, errors = validator.validate(graph)
        assert is_valid is False
        assert any("Circular dependency" in err for err in errors)

    def test_self_dependency(self):
        """节点依赖自己应该被检测到"""
        graph = TaskGraph(
            workflow_id="test_8",
            nodes=[
                TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={}, depends_on=["node_1"]),
            ]
        )
        validator = GraphValidator()
        is_valid, errors = validator.validate(graph)
        assert is_valid is False
        assert any("Circular dependency" in err for err in errors)


class TestEmptyGraph:
    """测试空任务图"""

    def test_empty_nodes(self):
        """空节点列表应该通过验证"""
        graph = TaskGraph(workflow_id="test_empty", nodes=[])
        validator = GraphValidator()
        is_valid, errors = validator.validate(graph)
        assert is_valid is True


class TestValidateOrRaise:
    """测试 validate_or_raise 方法"""

    def test_valid_graph_no_exception(self):
        """有效图不抛出异常"""
        graph = TaskGraph(
            workflow_id="test_9",
            nodes=[TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={})]
        )
        validate_task_graph_or_raise(graph)

    def test_invalid_graph_raises_exception(self):
        """无效图抛出 GraphValidationError"""
        graph = TaskGraph(
            workflow_id="test_10",
            nodes=[
                TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={}, depends_on=["node_1"]),
            ]
        )
        with pytest.raises(GraphValidationError) as exc_info:
            validate_task_graph_or_raise(graph)
        assert "Circular dependency" in str(exc_info.value)


class TestConvenienceFunction:
    """测试便捷函数"""

    def test_validate_task_graph_valid(self):
        """便捷函数验证有效图"""
        graph = TaskGraph(
            workflow_id="test_11",
            nodes=[TaskNode(id="node_1", type=TaskType.CODE_EXECUTION, params={})]
        )
        is_valid, errors = validate_task_graph(graph)
        assert is_valid is True
        assert errors == []

    def test_validate_task_graph_invalid(self):
        """便捷函数验证无效图"""
        graph = TaskGraph(
            workflow_id="test_12",
            nodes=[
                TaskNode(id="node_1", type=TaskType.WEB_SEARCH, params={}, depends_on=["node_2"]),
                TaskNode(id="node_2", type=TaskType.CODE_EXECUTION, params={}, depends_on=["node_1"]),
            ]
        )
        is_valid, errors = validate_task_graph(graph)
        assert is_valid is False
        assert len(errors) > 0
