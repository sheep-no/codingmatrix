"""
aicloud Schema 模型

包含：
- ChatRequest / ChatResponse
- FileReadRequest / FileReadResponse
- FileWriteRequest / FileWriteResponse
- HistoryRequest / AuditLogRequest
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    session_id: Optional[str] = Field(None, description="会话 ID")
    model_id: Optional[str] = Field(None, description="模型 ID，默认使用系统默认模型")


class ChatResponse(BaseModel):
    session_id: str
    message: str
    model_id: str
    created_at: datetime


class ChatStreamRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    session_id: Optional[str] = Field(None, description="会话 ID")
    model_id: Optional[str] = Field(None, description="模型 ID")


class FileReadRequest(BaseModel):
    file_path: str = Field(..., description="文件路径")
    require_review: bool = Field(True, description="是否需要审查")


class FileReadResponse(BaseModel):
    content: str
    review_status: str
    filtered_content: Optional[str] = None
    review_id: Optional[str] = None


class FileWriteRequest(BaseModel):
    file_path: str = Field(..., description="文件路径")
    content: str = Field(..., description="文件内容")


class FileWriteResponse(BaseModel):
    success: bool
    review_status: str
    review_id: Optional[str] = None
    message: Optional[str] = None


class HistoryRequest(BaseModel):
    days: int = Field(10, ge=1, le=30, description="查询天数")


class AuditLogRequest(BaseModel):
    user_id: Optional[int] = Field(None, description="用户 ID")
    operation: Optional[str] = Field(None, description="操作类型")
    start_date: Optional[datetime] = Field(None, description="开始日期")
    end_date: Optional[datetime] = Field(None, description="结束日期")
    limit: int = Field(100, ge=1, le=1000, description="返回数量限制")


class AuditLogResponse(BaseModel):
    id: int
    user_id: int
    operation: str
    file_path: Optional[str] = None
    url: Optional[str] = None
    status: str
    details: Optional[str] = None
    created_at: datetime


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


class SessionResponse(BaseModel):
    id: str
    user_id: int
    created_at: datetime
    last_active_at: datetime
    messages: List[MessageResponse] = []


class ReviewResponse(BaseModel):
    id: str
    operation_type: str
    file_path: str
    status: str
    requested_by: int
    reviewed_by: Optional[int] = None
    ai_filter_passed: Optional[bool] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None


class ReviewActionRequest(BaseModel):
    review_id: str = Field(..., description="审查 ID")
    reason: Optional[str] = Field(None, description="操作原因")


class SessionSearchRequest(BaseModel):
    keyword: str = Field(..., description="搜索关键词")
    days: int = Field(10, ge=1, le=30, description="查询天数")


class SessionExportResponse(BaseModel):
    session_id: str
    exported_at: datetime
    message_count: int
    messages: List[MessageResponse]


class SessionDeleteResponse(BaseModel):
    success: bool
    deleted_session_id: str


class ModelInfoResponse(BaseModel):
    id: str
    name: str
    description: str
    max_tokens: int
    max_context: int
    capabilities: list
    is_default: bool
    cost_per_1m_input: float
    cost_per_1m_output: float
    tags: list


class ModelsListResponse(BaseModel):
    models: list
    default_model: str
    provider: dict


class CodeExecuteRequest(BaseModel):
    code: str = Field(..., description="要执行的代码")
    language: str = Field(..., description="编程语言 (python, javascript, go)")
    timeout: Optional[int] = Field(10, ge=1, le=30, description="超时时间（秒）")


class CodeExecuteResponse(BaseModel):
    success: bool
    output: str
    error: str
    exit_code: int
    execution_time: float
    language: str
