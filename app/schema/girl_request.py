# app/schema/girl_request.py
from datetime import datetime

from pydantic import BaseModel, Field
from typing import Optional, List


class GirlRequest(BaseModel):
    """虚拟姬对话请求"""
    prompt: str = Field(..., min_length=1, max_length=2000, description="用户输入的对话内容")
    temperature: Optional[float] = Field(default=None, ge=0.0, le=1.5, description="AI 温度")
    character_id: Optional[str] = Field(default="gentle", description="角色 ID (gentle/lively/tsundere/intellectual/companion)")
    max_tokens: Optional[int] = Field(default=None, ge=50, le=1000, description="最大 Token 数")


class GirlResponse(BaseModel):
    """AI 对话响应"""
    message: str = Field(..., description="AI 生成的回复内容")
    model: str = Field(..., description="使用的 AI 模型名称")
    tokens_used: int = Field(..., description="本次请求消耗的 token 数量")


class HistoryQuery(BaseModel):
    """历史记录查询参数"""
    limit: Optional[int] = Field(20, ge=1, le=100, description="返回的最大记录数")
    offset: Optional[int] = Field(0, ge=0, description="分页偏移量")
    start_date: Optional[datetime] = Field(None, description="查询开始时间")
    end_date: Optional[datetime] = Field(None, description="查询结束时间")


class HistoryRecord(BaseModel):
    """单条历史记录"""
    id: str
    role: str
    content: str
    model: Optional[str]
    token_usage: Optional[int]
    created_at: datetime


class HistoryResponse(BaseModel):
    """历史记录响应"""
    total: int
    records: List[HistoryRecord]
    has_more: bool
