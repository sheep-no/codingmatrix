"""
Ephemeral Workflow Schema - Pydantic 数据模型

定义临时工作流的请求、响应和内部数据结构
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime


class TaskType(str, Enum):
    """任务节点类型枚举"""
    WEB_SEARCH = "web_search"
    CODE_EXECUTION = "code_execution"
    CHART_GENERATION = "chart_generation"
    FILE_PROCESSING = "file_processing"


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStatus(str, Enum):
    """工作流状态枚举"""
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskNode(BaseModel):
    """任务节点模型"""
    id: str = Field(..., description="节点唯一标识")
    type: TaskType = Field(..., description="节点类型")
    params: Dict[str, Any] = Field(default_factory=dict, description="节点参数")
    depends_on: List[str] = Field(default_factory=list, description="依赖的节点 ID 列表")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="节点状态")
    result: Optional[Any] = Field(None, description="节点执行结果")
    error: Optional[str] = Field(None, description="节点执行错误信息")


class TaskGraph(BaseModel):
    """任务图模型"""
    workflow_id: str = Field(..., description="工作流唯一标识")
    version: str = Field(default="1.0", description="任务图版本")
    nodes: List[TaskNode] = Field(default_factory=list, description="任务节点列表")
    timeout: int = Field(default=1800, description="超时时间（秒）")
    exportable: bool = Field(default=True, description="是否可导出")


class WorkflowRequest(BaseModel):
    """工作流执行请求"""
    natural_language_request: str = Field(..., description="自然语言任务描述")
    export_workflow: bool = Field(default=False, description="是否导出工作流 JSON")
    timeout: int = Field(default=1800, ge=60, le=3600, description="超时时间（秒）")
    session_id: Optional[str] = Field(None, description="会话 ID（用于继续生成）")


class WorkflowStatusResponse(BaseModel):
    """工作流状态响应"""
    workflow_id: str
    status: WorkflowStatus
    task_graph: Optional[TaskGraph] = None
    created_at: datetime
    updated_at: datetime


class WorkflowStreamEvent(BaseModel):
    """工作流流式事件"""
    event_type: str = Field(..., description="事件类型")
    workflow_id: str = Field(..., description="工作流 ID")
    node_id: Optional[str] = Field(None, description="节点 ID")
    status: Optional[str] = Field(None, description="状态")
    data: Optional[Any] = Field(None, description="事件数据")
    timestamp: datetime = Field(default_factory=datetime.now)


class WorkflowErrorResponse(BaseModel):
    """工作流错误响应"""
    error: str = Field(..., description="错误类型")
    message: str = Field(..., description="错误消息")
    workflow_id: Optional[str] = Field(None, description="工作流 ID")
    node_id: Optional[str] = Field(None, description="节点 ID")
    details: Optional[Dict[str, Any]] = Field(None, description="错误详情")
