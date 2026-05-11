"""
任务队列 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum


class TaskStatusEnum(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class TaskTypeEnum(str, Enum):
    """任务类型"""
    PROJECT_GENERATE = "project_generate"
    CODE_GENERATE = "code_generate"
    PPT_GENERATE = "ppt_generate"
    FILE_PROCESS = "file_process"


class TaskPriorityEnum(str, Enum):
    """任务优先级"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskCreateRequest(BaseModel):
    """创建任务请求"""
    task_type: TaskTypeEnum
    priority: TaskPriorityEnum = TaskPriorityEnum.MEDIUM
    timeout: Optional[int] = Field(default=300, ge=30, le=3600)
    params: Dict[str, Any] = Field(default_factory=dict)
    input_file_id: Optional[int] = None
    parent_task_id: Optional[int] = None


class TaskResponse(BaseModel):
    """任务响应"""
    task_id: str
    celery_task_id: Optional[str] = None
    task_type: str
    status: str
    priority: int = 5
    progress: int = 0
    progress_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    parent_task_id: Optional[int] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    """任务列表响应"""
    total: int
    tasks: List[TaskResponse]
    page: int
    page_size: int
