app/schemas.py
"""
API 请求/响应数据结构定义。
使用 Pydantic 框架定义 FastAPI 的请求和响应模型。
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TodoCreate(BaseModel):
    """TODO 创建请求模型。"""
    title: str = Field(..., min_length=1, max_length=255, description="标题")
    description: Optional[str] = Field(None, max_length=1000, description="描述")


class TodoUpdate(BaseModel):
    """TODO 更新请求模型。"""
    title: Optional[str] = Field(None, min_length=1, max_length=255, description="标题")
    description: Optional[str] = Field(None, max_length=1000, description="描述")


class TodoRead(BaseModel):
    """TODO 读取响应模型。"""
    id: int
    title: str
    description: Optional[str]
    completed: bool
    created_at: datetime
    updated_at: datetime
    database = False  # Pydantic 从 ORM 属性读取数据的配置