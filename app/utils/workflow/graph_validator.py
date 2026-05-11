"""
Graph Validator - 任务图验证器

验证任务图的：
1. 循环依赖检测（使用 Kahn 算法）
2. 节点完整性验证
3. 节点类型有效性验证
"""

import logging
from typing import List, Dict, Set, Tuple, Optional
from collections import deque

from app.schema.workflow import TaskGraph, TaskNode, TaskType

logger = logging.getLogger(__name__)


class GraphValidationError(Exception):
    """任务图验证异常"""
    def __init__(self, message: str, errors: List[str] = None):
        super().__init__(message)
        self.errors = errors or [message]


class GraphValidator:
    """
    任务图验证器

    验证任务图的：
    - 循环依赖检测
    - 节点 ID 唯一性
    - 依赖节点存在性
    - 节点类型有效性
    """

    def __init__(self):
        self.errors: List[str] = []

    def validate(self, task_graph: TaskGraph) -> Tuple[bool, List[str]]:
        """
        验证任务图

        Args:
            task_graph: 要验证的任务图

        Returns:
            (是否有效, 错误列表)
        """
        self.errors = []

        self._check_node_id_uniqueness(task_graph)
        self._check_dependency_existence(task_graph)
        self._check_task_type_validity(task_graph)
        self._check_circular_dependency(task_graph)

        return len(self.errors) == 0, self.errors

    def _check_node_id_uniqueness(self, task_graph: TaskGraph) -> None:
        """检查节点 ID 唯一性"""
        node_ids = [node.id for node in task_graph.nodes]
        if len(node_ids) != len(set(node_ids)):
            duplicate_ids = set([id for id in node_ids if node_ids.count(id) > 1])
            self.errors.append(f"Duplicate node ID found: {duplicate_ids}")

    def _check_dependency_existence(self, task_graph: TaskGraph) -> None:
        """检查依赖节点是否存在"""
        node_ids = {node.id for node in task_graph.nodes}
        for node in task_graph.nodes:
            for dep_id in node.depends_on:
                if dep_id not in node_ids:
                    self.errors.append(f"Node '{node.id}' depends on non-existent node '{dep_id}'")

    def _check_task_type_validity(self, task_graph: TaskGraph) -> None:
        """检查任务类型有效性"""
        valid_types = set(TaskType)
        for node in task_graph.nodes:
            if node.type not in valid_types:
                self.errors.append(
                    f"Node '{node.id}' has invalid type '{node.type}'. "
                    f"Valid types: {[t.value for t in valid_types]}"
                )

    def _check_circular_dependency(self, task_graph: TaskGraph) -> None:
        """使用 Kahn 算法检测循环依赖"""
        if not task_graph.nodes:
            return

        node_ids = {node.id for node in task_graph.nodes}
        in_degree: Dict[str, int] = {node.id: 0 for node in task_graph.nodes}
        adjacency: Dict[str, List[str]] = {node.id: [] for node in task_graph.nodes}

        for node in task_graph.nodes:
            for dep_id in node.depends_on:
                if dep_id in node_ids:
                    adjacency[dep_id].append(node.id)
                    in_degree[node.id] += 1

        queue = deque([node_id for node_id, degree in in_degree.items() if degree == 0])
        visited_count = 0

        while queue:
            current = queue.popleft()
            visited_count += 1
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(task_graph.nodes):
            cyclic_nodes = [
                node_id for node_id, degree in in_degree.items() if degree > 0
            ]
            self.errors.append(f"Circular dependency detected involving nodes: {cyclic_nodes}")

    def validate_or_raise(self, task_graph: TaskGraph) -> None:
        """
        验证任务图，无效则抛出异常

        Args:
            task_graph: 要验证的任务图

        Raises:
            GraphValidationError: 当验证失败时
        """
        is_valid, errors = self.validate(task_graph)
        if not is_valid:
            error_details = "; ".join(errors)
            raise GraphValidationError(
                f"Task graph validation failed: {error_details}",
                errors=errors
            )


def validate_task_graph(task_graph: TaskGraph) -> Tuple[bool, List[str]]:
    """
    便捷函数：验证任务图

    Args:
        task_graph: 要验证的任务图

    Returns:
        (是否有效, 错误列表)
    """
    validator = GraphValidator()
    return validator.validate(task_graph)


def validate_task_graph_or_raise(task_graph: TaskGraph) -> None:
    """
    便捷函数：验证任务图，无效则抛出异常

    Args:
        task_graph: 要验证的任务图

    Raises:
        GraphValidationError: 当验证失败时
    """
    validator = GraphValidator()
    validator.validate_or_raise(task_graph)
