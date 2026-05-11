"""
Workflow Executor - 工作流执行器

核心执行引擎：
1. 拓扑排序确定执行顺序
2. 并发/串行执行节点
3. 错误隔离（单个失败不影响其他）
4. 超时控制
5. 资源清理
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Set, Callable, AsyncGenerator
from datetime import datetime
from collections import deque

from app.schema.workflow import TaskGraph, TaskNode, TaskType, TaskStatus, WorkflowStatus
from app.utils.workflow.graph_validator import GraphValidator, GraphValidationError
from app.utils.workflow.state_machine import WorkflowStateMachine
from app.utils.workflow.result_aggregator import ResultAggregator
from app.utils.workflow.node_types.base import NodeResult
from app.utils.workflow.node_types.chart_generation import cleanup_all_temp_files
from app.utils.workflow.node_types import (
    TaskNodeBase,
    WebSearchNode,
    CodeExecutionNode,
    ChartGenerationNode,
    FileProcessingNode,
)

logger = logging.getLogger(__name__)


class WorkflowExecutorError(Exception):
    """工作流执行器异常"""
    pass


class NodeFactory:
    """节点工厂，根据类型创建节点实例"""

    _NODE_CLASSES = {
        TaskType.WEB_SEARCH: WebSearchNode,
        TaskType.CODE_EXECUTION: CodeExecutionNode,
        TaskType.CHART_GENERATION: ChartGenerationNode,
        TaskType.FILE_PROCESSING: FileProcessingNode,
    }

    @classmethod
    def create(cls, node: TaskNode) -> TaskNodeBase:
        """创建节点实例"""
        node_class = cls._NODE_CLASSES.get(node.type)
        if node_class is None:
            raise WorkflowExecutorError(f"Unsupported node type: {node.type}")
        return node_class(node_id=node.id, params=node.params)


class WorkflowExecutor:
    """
    工作流执行器

    核心功能：
    - 任务图验证
    - 拓扑排序执行
    - 并发执行（独立节点）
    - 错误隔离
    - 超时控制
    - 资源清理
    """

    def __init__(
        self,
        task_graph: TaskGraph,
        timeout: int = 1800,
        node_timeout: int = 300,
        max_concurrent: int = 3,
    ):
        """
        初始化执行器

        Args:
            task_graph: 任务图
            timeout: 工作流超时（秒）
            node_timeout: 节点超时（秒）
            max_concurrent: 最大并发数
        """
        self.task_graph = task_graph
        self.timeout = timeout
        self.node_timeout = node_timeout
        self.max_concurrent = max_concurrent

        self._validator = GraphValidator()
        self._state_machine: Optional[WorkflowStateMachine] = None
        self._aggregator: Optional[ResultAggregator] = None
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._cancel_event: Optional[asyncio.Event] = None
        self._cleanup_callbacks: List[Callable] = []

        self._cleanup_callbacks.append(cleanup_all_temp_files)

    def validate(self) -> None:
        """
        验证任务图

        Raises:
            GraphValidationError: 验证失败
        """
        self._validator.validate_or_raise(self.task_graph)

    def _compute_topological_order(self) -> List[str]:
        """
        计算拓扑排序

        Returns:
            节点 ID 列表（按执行顺序）
        """
        in_degree: Dict[str, int] = {node.id: 0 for node in self.task_graph.nodes}
        adjacency: Dict[str, List[str]] = {node.id: [] for node in self.task_graph.nodes}

        for node in self.task_graph.nodes:
            for dep_id in node.depends_on:
                adjacency[dep_id].append(node.id)
                in_degree[node.id] += 1

        queue = deque([node_id for node_id, degree in in_degree.items() if degree == 0])
        result = []

        while queue:
            current = queue.popleft()
            result.append(current)

            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result

    def _get_executable_nodes(
        self,
        completed: Set[str],
        failed: Set[str],
        running: Set[str],
    ) -> List[str]:
        """
        获取可执行的节点

        条件：
        1. 未完成
        2. 未运行
        3. 所有依赖都已完成

        Args:
            completed: 已完成的节点
            failed: 失败的节点
            running: 正在运行的节点

        Returns:
            可执行节点列表
        """
        executable = []

        for node in self.task_graph.nodes:
            if node.id in completed or node.id in running:
                continue

            deps_completed = all(dep in completed for dep in node.depends_on)
            if deps_completed:
                executable.append(node.id)

        return executable

    async def _execute_node(
        self,
        node_id: str,
        context: Dict[str, Any],
        cancel_event: asyncio.Event,
    ) -> NodeResult:
        """
        执行单个节点

        Args:
            node_id: 节点 ID
            context: 执行上下文
            cancel_event: 取消事件

        Returns:
            节点执行结果
        """
        try:
            for task_node in self.task_graph.nodes:
                if task_node.id == node_id:
                    break
            else:
                return NodeResult.error_result(error=f"Node {node_id} not found")

            node_instance = NodeFactory.create(task_node)

            errors = node_instance.validate_params()
            if errors:
                return NodeResult.error_result(
                    error=f"Invalid params: {', '.join(errors)}"
                )

            logger.info(f"[{node_id}] 开始执行")

            try:
                async with asyncio.timeout(self.node_timeout):
                    result = await node_instance.execute(context)
                    return result
            except asyncio.TimeoutError:
                return NodeResult.error_result(
                    error=f"Node execution timeout after {self.node_timeout} seconds"
                )

        except Exception as e:
            error_msg = f"Node execution error: {str(e)}"
            logger.error(f"[{node_id}] {error_msg}")
            return NodeResult.error_result(error=error_msg)

    async def execute(
        self,
        on_node_start: Callable[[str], None] = None,
        on_node_complete: Callable[[str, NodeResult], None] = None,
        on_workflow_complete: Callable[[Dict], None] = None,
    ) -> Dict[str, Any]:
        """
        执行工作流

        Args:
            on_node_start: 节点开始回调
            on_node_complete: 节点完成回调
            on_workflow_complete: 工作流完成回调

        Returns:
            执行结果字典
        """
        self.validate()

        workflow_id = self.task_graph.workflow_id
        self._state_machine = WorkflowStateMachine(
            workflow_id, self.task_graph, self.timeout
        )
        self._aggregator = ResultAggregator(workflow_id, self.task_graph)
        self._cancel_event = asyncio.Event()

        self._state_machine.start_workflow()

        completed: Set[str] = set()
        failed: Set[str] = set()
        running: Set[str] = set()

        topological_order = self._compute_topological_order()
        order_index = {node_id: i for i, node_id in enumerate(topological_order)}

        logger.info(f"[{workflow_id}] 开始执行 | 节点数: {len(topological_order)}")

        try:
            while not self._state_machine.is_workflow_complete():
                if self._cancel_event.is_set():
                    break

                if self._state_machine.check_timeout():
                    logger.warning(f"[{workflow_id}] 工作流超时")
                    self._state_machine.cancel_workflow("Workflow timeout")
                    break

                executable = self._get_executable_nodes(completed, failed, running)

                if not executable and not running:
                    if failed:
                        logger.info(f"[{workflow_id}] 无法继续执行（失败节点阻塞）")
                    break

                while executable and len(running) < self.max_concurrent:
                    node_id = executable.pop(0)
                    running.add(node_id)

                    self._state_machine.start_node(node_id)
                    if on_node_start:
                        on_node_start(node_id)

                    context = self._aggregator.get_context(node_id)

                    task = asyncio.create_task(
                        self._execute_node(node_id, context, self._cancel_event)
                    )
                    self._running_tasks[node_id] = task

                if running:
                    done, pending = await asyncio.wait(
                        self._running_tasks.values(),
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    for task in done:
                        node_id = None
                        for nid, t in self._running_tasks.items():
                            if t == task:
                                node_id = nid
                                break

                        if node_id:
                            result = task.result()
                            self._running_tasks.pop(node_id)
                            running.remove(node_id)

                            self._aggregator.record_result(node_id, result)

                            if result.success:
                                completed.add(node_id)
                                self._state_machine.complete_node(node_id, result.data)
                            else:
                                failed.add(node_id)
                                self._state_machine.fail_node(node_id, result.error)

                            if on_node_complete:
                                on_node_complete(node_id, result)

                await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            logger.info(f"[{workflow_id}] 工作流被取消")
            self._state_machine.cancel_workflow("User cancelled")
            for task in self._running_tasks.values():
                task.cancel()
        finally:
            await self._cleanup()

        summary = self._aggregator.get_workflow_summary()

        if on_workflow_complete:
            on_workflow_complete(summary)

        return {
            "workflow_id": workflow_id,
            "status": self._state_machine.get_status().value,
            "summary": summary,
        }

    async def _cleanup(self) -> None:
        """清理资源"""
        logger.info("执行资源清理")

        for callback in self._cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Cleanup callback error: {e}")

        self._running_tasks.clear()

    def register_cleanup(self, callback: Callable) -> None:
        """
        注册清理回调

        Args:
            callback: 清理回调函数
        """
        self._cleanup_callbacks.append(callback)

    def cancel(self) -> None:
        """取消工作流执行"""
        if self._cancel_event:
            self._cancel_event.set()

    def get_state_machine(self) -> Optional[WorkflowStateMachine]:
        """获取状态机"""
        return self._state_machine

    def get_aggregator(self) -> Optional[ResultAggregator]:
        """获取结果聚合器"""
        return self._aggregator
