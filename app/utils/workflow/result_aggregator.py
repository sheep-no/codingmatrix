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
        self._node_map: Dict[str, TaskNode] = {node.id: node for node in task_graph.nodes}

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
        # 节点启动时尚未 record 结果，这里按需构建，否则执行期拿不到上游数据
        context = self._build_node_context(node_id)
        self._node_contexts[node_id] = context
        return context

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

        node = self._node_map.get(node_id)
        inject_ids = []
        if node:
            context["node_type"] = node.type.value
            context["params"] = dict(node.params)
            context["depends_on"] = node.depends_on
            # 只注入直接依赖的结果，避免每次记录全量遍历已有结果
            inject_ids.extend(node.depends_on)

        # 节点自身已有结果时一并注入，保持既有上下文契约
        if node_id in self._node_results:
            inject_ids.append(node_id)

        for dep_id in inject_ids:
            result = self._node_results.get(dep_id)
            if result is None:
                continue
            if result.success:
                context[f"{dep_id}_result"] = result.data
                context[f"{dep_id}_error"] = None
            else:
                context[f"{dep_id}_result"] = None
                context[f"{dep_id}_error"] = result.error

            # 产出节点声明的 output_variable 也映射进上下文，否则 LLM 规划出的
            # 语义变量名（如 llm_result）下游 input_variable 永远读不到
            dep_node = self._node_map.get(dep_id)
            if dep_node:
                output_variable = (dep_node.params or {}).get("output_variable")
                if output_variable and output_variable not in context:
                    context[output_variable] = result.data if result.success else None

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
            "execution_order": self._completed_order.copy(),
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

        while True:
            # 先补发增量再判断完成，否则最后一个节点的完成事件会丢失
            current_count = len(self._node_results)
            for node_id in self._completed_order[last_count:current_count]:
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

            last_count = current_count

            if self.is_complete():
                break

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
