"""
Task Node Base - 任务节点基类

定义所有任务节点的抽象基类和接口
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from dataclasses import dataclass
from enum import Enum

from app.schema.workflow import TaskType


class NodeExecutionMode(str, Enum):
    """节点执行模式"""
    SYNCHRONOUS = "synchronous"
    ASYNCHRONOUS = "asynchronous"


@dataclass
class NodeResult:
    """节点执行结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    @classmethod
    def success_result(cls, data: Any, metadata: Dict[str, Any] = None) -> "NodeResult":
        """创建成功结果"""
        return cls(success=True, data=data, metadata=metadata or {})

    @classmethod
    def error_result(cls, error: str, metadata: Dict[str, Any] = None) -> "NodeResult":
        """创建错误结果"""
        return cls(success=False, error=error, metadata=metadata or {})


class TaskNodeBase(ABC):
    """
    任务节点抽象基类

    所有任务节点类型必须继承此类并实现：
    - task_type: 节点类型
    - execute(): 执行逻辑
    - validate_params(): 参数验证
    """

    task_type: TaskType = None

    def __init__(self, node_id: str, params: Dict[str, Any]):
        """
        初始化节点

        Args:
            node_id: 节点唯一标识
            params: 节点参数
        """
        self.node_id = node_id
        self.params = params

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """
        执行节点任务

        Args:
            context: 执行上下文，包含依赖节点的输出

        Returns:
            NodeResult: 执行结果
        """
        pass

    @abstractmethod
    def validate_params(self) -> List[str]:
        """
        验证参数

        Returns:
            List[str]: 错误列表，空列表表示参数有效
        """
        pass

    def get_required_params(self) -> List[str]:
        """
        获取必需参数列表

        子类可以重写此方法声明必需参数

        Returns:
            List[str]: 必需参数名列表
        """
        return []

    def get_optional_params(self) -> Dict[str, Any]:
        """
        获取可选参数及其默认值

        子类可以重写此方法声明可选参数

        Returns:
            Dict[str, Any]: 可选参数字典
        """
        return {}

    def merge_context(self, context: Dict[str, Any], upstream_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        合并上游节点输出到上下文

        Args:
            context: 当前上下文
            upstream_results: 上游节点结果字典

        Returns:
            Dict[str, Any]: 合并后的上下文
        """
        merged = context.copy()

        for node_id, result in upstream_results.items():
            if result.success:
                merged[f"{node_id}_result"] = result.data
                merged[f"{node_id}_error"] = None
            else:
                merged[f"{node_id}_result"] = None
                merged[f"{node_id}_error"] = result.error

        return merged

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(node_id={self.node_id}, type={self.task_type})>"
