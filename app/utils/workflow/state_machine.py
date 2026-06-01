"""
Workflow State Machine - 内存状态机

管理临时工作流的执行状态，包括：
1. 工作流级别状态管理
2. 任务节点级别状态管理
3. 状态变更回调机制
4. 超时检测
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict

from app.schema.workflow import TaskGraph, TaskNode, TaskStatus, WorkflowStatus

logger = logging.getLogger(__name__)


class WorkflowState(str, Enum):
    """工作流状态枚举"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class NodeState:
    """节点状态"""
    node_id: str
    status: TaskStatus = TaskStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Any = None
    retry_count: int = 0


@dataclass
class WorkflowStateSnapshot:
    """工作流状态快照"""
    workflow_id: str
    status: WorkflowStatus
    nodes: Dict[str, NodeState]
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class StateTransitionError(Exception):
    """状态转换异常"""
    pass


class WorkflowStateMachine:
    """
    工作流状态机

    管理工作流的完整生命周期：
    - 初始化工作流状态
    - 更新节点状态
    - 追踪执行进度
    - 超时检测
    - 状态变更回调
    """

    def __init__(self, workflow_id: str, task_graph: TaskGraph, timeout: int = 1800):
        """
        初始化状态机

        Args:
            workflow_id: 工作流唯一标识
            task_graph: 任务图
            timeout: 超时时间（秒）
        """
        self.workflow_id = workflow_id
        self.task_graph = task_graph
        self.timeout = timeout

        self._status = WorkflowStatus.CREATED
        self._nodes: Dict[str, NodeState] = {}
        self._created_at = datetime.now()
        self._started_at: Optional[datetime] = None
        self._completed_at: Optional[datetime] = None
        self._error: Optional[str] = None
        self._lock = asyncio.Lock()

        self._callbacks: Dict[str, List[Callable]] = defaultdict(list)

        self._initialize_nodes()

    def _initialize_nodes(self) -> None:
        """初始化所有节点状态"""
        for node in self.task_graph.nodes:
            self._nodes[node.id] = NodeState(node_id=node.id)

    def get_status(self) -> WorkflowStatus:
        """获取当前工作流状态"""
        return self._status

    def get_node_status(self, node_id: str) -> Optional[TaskStatus]:
        """获取指定节点状态"""
        if node_id in self._nodes:
            return self._nodes[node_id].status
        return None

    def get_node_state(self, node_id: str) -> Optional[NodeState]:
        """获取节点状态对象"""
        return self._nodes.get(node_id)

    def get_all_node_states(self) -> Dict[str, NodeState]:
        """获取所有节点状态"""
        return self._nodes.copy()

    def get_pending_nodes(self) -> List[str]:
        """获取待执行的节点 ID 列表"""
        return [
            node_id for node_id, state in self._nodes.items()
            if state.status == TaskStatus.PENDING
        ]

    def get_running_nodes(self) -> List[str]:
        """获取正在执行的节点 ID 列表"""
        return [
            node_id for node_id, state in self._nodes.items()
            if state.status == TaskStatus.RUNNING
        ]

    def get_completed_nodes(self) -> List[str]:
        """获取已完成的节点 ID 列表"""
        return [
            node_id for node_id, state in self._nodes.items()
            if state.status == TaskStatus.COMPLETED
        ]

    def get_failed_nodes(self) -> List[str]:
        """获取失败的节点 ID 列表"""
        return [
            node_id for node_id, state in self._nodes.items()
            if state.status == TaskStatus.FAILED
        ]

    def is_workflow_complete(self) -> bool:
        """检查工作流是否完成（成功或失败）"""
        return self._status in (
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED
        )

    def is_node_executable(self, node_id: str) -> bool:
        """
        检查节点是否可以执行

        条件：
        1. 节点状态为 pending
        2. 所有依赖节点都已完成
        """
        if node_id not in self._nodes:
            return False

        node_state = self._nodes[node_id]
        if node_state.status != TaskStatus.PENDING:
            return False

        for node in self.task_graph.nodes:
            if node.id == node_id:
                for dep_id in node.depends_on:
                    if dep_id in self._nodes:
                        dep_state = self._nodes[dep_id]
                        if dep_state.status != TaskStatus.COMPLETED:
                            return False
                break

        return True

    def start_workflow(self) -> None:
        """启动工作流"""
        if self._status != WorkflowStatus.CREATED:
            raise StateTransitionError(
                f"Cannot start workflow from status: {self._status}"
            )

        self._status = WorkflowStatus.RUNNING
        self._started_at = datetime.now()
        self._emit_event("workflow_started", {"workflow_id": self.workflow_id})

    def start_node(self, node_id: str) -> None:
        """
        启动节点执行

        Args:
            node_id: 节点 ID
        """
        if node_id not in self._nodes:
            raise StateTransitionError(f"Unknown node: {node_id}")

        node_state = self._nodes[node_id]

        if node_state.status != TaskStatus.PENDING:
            raise StateTransitionError(
                f"Cannot start node {node_id} from status: {node_state.status}"
            )

        node_state.status = TaskStatus.RUNNING
        node_state.started_at = datetime.now()
        self._emit_event("node_started", {
            "workflow_id": self.workflow_id,
            "node_id": node_id
        })

    def complete_node(self, node_id: str, result: Any = None) -> None:
        """
        完成节点执行

        Args:
            node_id: 节点 ID
            result: 执行结果
        """
        if node_id not in self._nodes:
            raise StateTransitionError(f"Unknown node: {node_id}")

        node_state = self._nodes[node_id]

        if node_state.status != TaskStatus.RUNNING:
            raise StateTransitionError(
                f"Cannot complete node {node_id} from status: {node_state.status}"
            )

        node_state.status = TaskStatus.COMPLETED
        node_state.completed_at = datetime.now()
        node_state.result = result

        self._emit_event("node_completed", {
            "workflow_id": self.workflow_id,
            "node_id": node_id,
            "result": result
        })

        self._check_workflow_completion()

    def fail_node(self, node_id: str, error: str) -> None:
        """
        标记节点失败

        Args:
            node_id: 节点 ID
            error: 错误信息
        """
        if node_id not in self._nodes:
            raise StateTransitionError(f"Unknown node: {node_id}")

        node_state = self._nodes[node_id]

        if node_state.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            raise StateTransitionError(
                f"Cannot fail node {node_id} from status: {node_state.status}"
            )

        node_state.status = TaskStatus.FAILED
        node_state.completed_at = datetime.now()
        node_state.error = error

        self._emit_event("node_failed", {
            "workflow_id": self.workflow_id,
            "node_id": node_id,
            "error": error
        })

        if self._status == WorkflowStatus.RUNNING:
            self._check_workflow_stuck()

    def _check_workflow_stuck(self) -> None:
        """
        检查工作流是否陷入困境（无法继续执行）

        当有失败节点且没有可执行的节点时，工作流应该标记为失败
        """
        has_failed = any(
            state.status == TaskStatus.FAILED
            for state in self._nodes.values()
        )

        if not has_failed:
            return

        executable_nodes = [
            node_id for node_id in self._nodes.keys()
            if self.is_node_executable(node_id)
        ]

        if len(executable_nodes) == 0:
            self._status = WorkflowStatus.FAILED
            self._completed_at = datetime.now()
            self._error = "Workflow stuck: failed nodes block all remaining paths"
            self._emit_event("workflow_stuck", {
                "workflow_id": self.workflow_id,
                "failed_nodes": self.get_failed_nodes()
            })

    def cancel_workflow(self, reason: str = None) -> None:
        """
        取消工作流

        Args:
            reason: 取消原因
        """
        if self.is_workflow_complete():
            raise StateTransitionError(
                f"Cannot cancel workflow in status: {self._status}"
            )

        self._status = WorkflowStatus.CANCELLED
        self._completed_at = datetime.now()
        self._error = reason

        for node_id, node_state in self._nodes.items():
            if node_state.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                node_state.status = TaskStatus.FAILED
                node_state.error = f"Cancelled: {reason or 'User cancelled'}"

        self._emit_event("workflow_cancelled", {
            "workflow_id": self.workflow_id,
            "reason": reason
        })

    def check_timeout(self) -> bool:
        """
        检查工作流是否超时

        Returns:
            True if timeout exceeded
        """
        if self._started_at is None:
            return False

        elapsed = (datetime.now() - self._started_at).total_seconds()
        if elapsed > self.timeout:
            return True
        return False

    def check_node_timeout(self, node_id: str, node_timeout: int = 300) -> bool:
        """
        检查节点是否超时

        Args:
            node_id: 节点 ID
            node_timeout: 节点超时时间（秒）

        Returns:
            True if node timeout exceeded
        """
        if node_id not in self._nodes:
            return False

        node_state = self._nodes[node_id]
        if node_state.started_at is None:
            return False

        elapsed = (datetime.now() - node_state.started_at).total_seconds()
        return elapsed > node_timeout

    def get_snapshot(self) -> WorkflowStateSnapshot:
        """
        获取工作流状态快照

        Returns:
            工作流状态快照
        """
        return WorkflowStateSnapshot(
            workflow_id=self.workflow_id,
            status=self._status,
            nodes=self._nodes.copy(),
            created_at=self._created_at,
            started_at=self._started_at,
            completed_at=self._completed_at,
            error=self._error
        )

    def register_callback(self, event: str, callback: Callable) -> None:
        """
        注册状态变更回调

        Args:
            event: 事件类型
            callback: 回调函数
        """
        self._callbacks[event].append(callback)

    def _emit_event(self, event: str, data: Dict[str, Any]) -> None:
        """
        触发状态变更事件

        Args:
            event: 事件类型
            data: 事件数据
        """
        if event in self._callbacks:
            for callback in self._callbacks[event]:
                try:
                    callback(data)
                except Exception as e:
                    logger.error(f"Callback error for event {event}: {e}")

    def _check_workflow_completion(self) -> None:
        """检查工作流是否应该完成"""
        all_nodes_done = all(
            state.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
            for state in self._nodes.values()
        )

        if not all_nodes_done:
            return

        has_failed = any(
            state.status == TaskStatus.FAILED
            for state in self._nodes.values()
        )

        if has_failed:
            self._status = WorkflowStatus.FAILED
            self._completed_at = datetime.now()
            self._error = "One or more nodes failed"
            self._emit_event("workflow_failed", {
                "workflow_id": self.workflow_id,
                "failed_nodes": self.get_failed_nodes()
            })
        else:
            self._status = WorkflowStatus.COMPLETED
            self._completed_at = datetime.now()
            self._emit_event("workflow_completed", {
                "workflow_id": self.workflow_id
            })

    def get_execution_summary(self) -> Dict[str, Any]:
        """
        获取执行摘要

        Returns:
            执行摘要字典
        """
        return {
            "workflow_id": self.workflow_id,
            "status": self._status.value,
            "total_nodes": len(self._nodes),
            "pending": len(self.get_pending_nodes()),
            "running": len(self.get_running_nodes()),
            "completed": len(self.get_completed_nodes()),
            "failed": len(self.get_failed_nodes()),
            "created_at": self._created_at.isoformat() if self._created_at else None,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "completed_at": self._completed_at.isoformat() if self._completed_at else None,
            "elapsed_seconds": (
                (datetime.now() - self._started_at).total_seconds()
                if self._started_at else None
            )
        }
