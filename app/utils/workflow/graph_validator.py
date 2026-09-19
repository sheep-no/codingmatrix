"""
Graph Validator - 任务图验证器

验证任务图的：
1. 循环依赖检测（使用 Kahn 算法）
2. 节点完整性验证
3. 节点类型有效性验证
"""

import logging
from typing import List, Dict, Set, Tuple, Optional
from collections import Counter, deque

from app.schema.workflow import TaskGraph, TaskNode, TaskType

logger = logging.getLogger(__name__)

# TaskType -> 节点类 的缓存。节点类构造与 validate_params 均为纯本地逻辑，
# 延迟 import 是为了避免在 graph_validator 模块加载时连带引入 matplotlib 等重量依赖。
_NODE_CLASS_CACHE: Optional[Dict[TaskType, type]] = None


def _get_node_classes() -> Dict[TaskType, type]:
    """延迟构建 TaskType -> 节点类 的映射"""
    global _NODE_CLASS_CACHE
    if _NODE_CLASS_CACHE is not None:
        return _NODE_CLASS_CACHE

    classes: Dict[TaskType, type] = {}
    try:
        from app.utils.workflow.node_types import (
            WebSearchNode,
            CodeExecutionNode,
            ChartGenerationNode,
            FileProcessingNode,
            LLMCallNode,
            ConditionalNode,
            HumanApprovalNode,
            HTTPRequestNode,
            DataTransformNode,
        )

        for node_cls in (
            WebSearchNode,
            CodeExecutionNode,
            ChartGenerationNode,
            FileProcessingNode,
            LLMCallNode,
            ConditionalNode,
            HumanApprovalNode,
            HTTPRequestNode,
            DataTransformNode,
        ):
            if node_cls.task_type is not None:
                classes[node_cls.task_type] = node_cls
    except Exception as e:  # 依赖缺失时不阻断结构校验
        logger.warning(f"加载节点类型失败，跳过参数语义校验: {e}")

    _NODE_CLASS_CACHE = classes
    return classes


class GraphValidationError(Exception):
    """任务图验证异常"""
    def __init__(self, message: str, errors: List[str] = None):
        super().__init__(message)
        self.errors = errors or [message]


class GraphValidator:
    """
    任务图验证器

    验证任务图的：
    - 图规模上限
    - 循环依赖检测
    - 节点 ID 唯一性
    - 依赖节点存在性
    - 节点类型有效性
    """

    # 单图节点数上限。LLM 分解与外部导入的图都不应达到该量级，
    # 设上限用于阻断超大图带来的校验/调度资源耗尽。
    MAX_NODES = 200

    def __init__(self, max_nodes: int = MAX_NODES):
        self.errors: List[str] = []
        self.max_nodes = max_nodes

    def validate(
        self,
        task_graph: TaskGraph,
        check_semantics: bool = False,
    ) -> Tuple[bool, List[str]]:
        """
        验证任务图

        Args:
            task_graph: 要验证的任务图
            check_semantics: 是否额外校验各节点 params 的语义（必填项/取值）。
                默认关闭以保持结构校验的既有契约；外部导入等需要拦截坏图
                的入口应显式开启。

        Returns:
            (是否有效, 错误列表)
        """
        self.errors = []

        self._check_graph_size(task_graph)
        self._check_node_id_uniqueness(task_graph)
        self._check_dependency_existence(task_graph)
        self._check_task_type_validity(task_graph)
        self._check_circular_dependency(task_graph)
        self._check_conditional_branches(task_graph)
        if check_semantics:
            self._check_node_params(task_graph)

        return len(self.errors) == 0, self.errors

    def _check_graph_size(self, task_graph: TaskGraph) -> None:
        """检查节点总数是否超过上限"""
        node_count = len(task_graph.nodes)
        if node_count > self.max_nodes:
            self.errors.append(
                f"Task graph has {node_count} nodes, exceeding the limit of {self.max_nodes}"
            )

    def _check_node_params(self, task_graph: TaskGraph) -> None:
        """校验各节点 params 是否满足其节点类型声明的必填项与取值约束"""
        node_classes = _get_node_classes()

        for node in task_graph.nodes:
            node_cls = node_classes.get(node.type)
            if node_cls is None:
                # 类型非法已由 _check_task_type_validity 覆盖
                continue
            try:
                instance = node_cls(node.id, node.params)
                for error in instance.validate_params():
                    self.errors.append(
                        f"Node '{node.id}' ({node.type.value}): {error}"
                    )
            except Exception as e:
                self.errors.append(f"Node '{node.id}' 参数校验异常: {e}")

    def _check_node_id_uniqueness(self, task_graph: TaskGraph) -> None:
        """检查节点 ID 唯一性"""
        node_ids = [node.id for node in task_graph.nodes]
        if len(node_ids) != len(set(node_ids)):
            # Counter 单次遍历，避免每个元素都对整个列表 count 造成 O(N^2)
            counts = Counter(node_ids)
            duplicate_ids = {node_id for node_id, count in counts.items() if count > 1}
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

    def _check_conditional_branches(self, task_graph: TaskGraph) -> None:
        """检查条件分支节点的分支引用是否有效"""
        node_ids = {node.id for node in task_graph.nodes}

        for node in task_graph.nodes:
            if node.type == TaskType.CONDITIONAL:
                true_branch = node.params.get("true_branch", [])
                false_branch = node.params.get("false_branch", [])

                for branch_id in true_branch + false_branch:
                    if branch_id not in node_ids:
                        self.errors.append(
                            f"Conditional node '{node.id}' references non-existent node '{branch_id}'"
                        )

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
