"""
Result Aggregator - 结果聚合器

收集和聚合工作流中各节点的执行结果：
1. 按依赖顺序收集结果
2. 构建节点执行上下文
3. 支持流式输出
"""

import logging
from typing import Dict, List, Any, Optional, AsyncGenerator
from datetime import datetime

from app.schema.workflow import TaskGraph, TaskNode, TaskStatus
from app.utils.workflow.node_types.base import NodeResult

logger = logging.getLogger(__name__)


class ResultAggregator:
    """
    结果聚合器

    收集工作流执行结果，构建执行上下文，支持流式输出
    """

    def __init__(self, workflow_id: str, task_graph: TaskGraph):
        """
        初始化结果聚合器

        Args:
            workflow_id: 工作流 ID
            task_graph: 任务图
        """
        self.workflow_id = workflow_id
        self.task_graph = task_graph

        self._node_results: Dict[str, NodeResult] = {}
        self._node_contexts: Dict[str, Dict[str, Any]] = {}
        self._completed_order: List[str] = []

    def record_result(self, node_id: str, result: NodeResult) -> None:
        """
        记录节点执行结果

        Args:
            node_id: 节点 ID
            result: 节点执行结果
        """
        self._node_results[node_id] = result
        self._completed_order.append(node_id)

        context = self._build_node_context(node_id)
        self._node_contexts[node_id] = context

        logger.info(
            f"[{self.workflow_id}] 记录结果: node={node_id}, "
            f"success={result.success}, order={len(self._completed_order)}"
        )

    def get_result(self, node_id: str) -> Optional[NodeResult]:
        """
        获取指定节点结果

        Args:
            node_id: 节点 ID

        Returns:
            节点结果或 None
        """
        return self._node_results.get(node_id)

    def get_context(self, node_id: str) -> Dict[str, Any]:
        """
        获取指定节点的执行上下文

        Args:
            node_id: 节点 ID

        Returns:
            节点执行上下文
        """
        return self._node_contexts.get(node_id, {})

    def get_upstream_results(self, node_id: str) -> Dict[str, NodeResult]:
        """
        获取上游节点结果

        Args:
            node_id: 节点 ID

        Returns:
            上游节点结果字典
        """
        upstream_results = {}

        for node in self.task_graph.nodes:
            if node.id == node_id:
                for dep_id in node.depends_on:
                    if dep_id in self._node_results:
                        upstream_results[dep_id] = self._node_results[dep_id]
                break

        return upstream_results

    def get_all_results(self) -> Dict[str, NodeResult]:
        """
        获取所有节点结果

        Returns:
            所有节点结果字典
        """
        return self._node_results.copy()

    def get_successful_results(self) -> Dict[str, NodeResult]:
        """
        获取所有成功的结果

        Returns:
            成功的节点结果字典
        """
        return {
            node_id: result
            for node_id, result in self._node_results.items()
            if result.success
        }

    def get_failed_results(self) -> Dict[str, NodeResult]:
        """
        获取所有失败的结果

        Returns:
            失败的节点结果字典
        """
        return {
            node_id: result
            for node_id, result in self._node_results.items()
            if not result.success
        }

    def is_complete(self) -> bool:
        """
        检查是否所有节点都已完成

        Returns:
            是否完成
        """
        return len(self._node_results) == len(self.task_graph.nodes)

    def get_completion_rate(self) -> float:
        """
        获取完成率

        Returns:
            完成率 (0.0 - 1.0)
        """
        if not self.task_graph.nodes:
            return 1.0
        return len(self._node_results) / len(self.task_graph.nodes)

    def get_execution_order(self) -> List[str]:
        """
        获取节点执行顺序

        Returns:
            节点 ID 列表（按执行顺序）
        """
        return self._completed_order.copy()

    def _build_node_context(self, node_id: str) -> Dict[str, Any]:
        """
        构建节点的执行上下文

        包含：
        1. 节点自己的结果
        2. 所有上游节点的结果

        Args:
            node_id: 节点 ID

        Returns:
            上下文字典
        """
        context = {
            "workflow_id": self.workflow_id,
            "node_id": node_id,
            "timestamp": datetime.now().isoformat(),
        }

        for node in self.task_graph.nodes:
            if node.id == node_id:
                context["node_type"] = node.type.value
                context["params"] = node.params
                context["depends_on"] = node.depends_on
                break

        for dep_id, result in self._node_results.items():
            if result.success:
                context[f"{dep_id}_result"] = result.data
                context[f"{dep_id}_error"] = None
            else:
                context[f"{dep_id}_result"] = None
                context[f"{dep_id}_error"] = result.error

        return context

    def get_workflow_summary(self) -> Dict[str, Any]:
        """
        获取工作流执行摘要

        Returns:
            执行摘要字典
        """
        total = len(self.task_graph.nodes)
        completed = len(self._node_results)
        successful = len(self.get_successful_results())
        failed = len(self.get_failed_results())

        return {
            "workflow_id": self.workflow_id,
            "total_nodes": total,
            "completed_nodes": completed,
            "pending_nodes": total - completed,
            "successful_nodes": successful,
            "failed_nodes": failed,
            "completion_rate": self.get_completion_rate(),
            "execution_order": self._completed_order,
        }

    async def stream_results(
        self,
        interval: float = 0.5
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式输出结果（用于 SSE）

        Args:
            interval: 轮询间隔（秒）

        Yields:
            结果更新事件
        """
        import asyncio

        last_count = 0

        while not self.is_complete():
            current_count = len(self._node_results)

            if current_count > last_count:
                last_count = current_count

                for node_id in self._completed_order[last_count - 1:]:
                    result = self._node_results[node_id]

                    yield {
                        "event": "node_completed",
                        "workflow_id": self.workflow_id,
                        "node_id": node_id,
                        "success": result.success,
                        "data": result.data if result.success else None,
                        "error": result.error if not result.success else None,
                        "completion_rate": self.get_completion_rate(),
                        "timestamp": datetime.now().isoformat(),
                    }

            await asyncio.sleep(interval)

        yield {
            "event": "workflow_completed",
            "workflow_id": self.workflow_id,
            "summary": self.get_workflow_summary(),
            "timestamp": datetime.now().isoformat(),
        }

    def export_results(self) -> Dict[str, Any]:
        """
        导出结果为可序列化格式

        Returns:
            结果字典
        """
        return {
            "workflow_id": self.workflow_id,
            "task_graph": {
                "workflow_id": self.task_graph.workflow_id,
                "version": self.task_graph.version,
                "nodes": [
                    {
                        "id": node.id,
                        "type": node.type.value,
                        "params": node.params,
                        "depends_on": node.depends_on,
                    }
                    for node in self.task_graph.nodes
                ],
            },
            "results": {
                node_id: {
                    "success": result.success,
                    "data": result.data,
                    "error": result.error,
                    "metadata": result.metadata,
                }
                for node_id, result in self._node_results.items()
            },
            "summary": self.get_workflow_summary(),
            "exported_at": datetime.now().isoformat(),
        }
