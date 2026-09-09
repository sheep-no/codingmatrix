from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.models import Todo
from app.schemas import TodoCreate, TodoResponse


class TodoUpdate(BaseModel):
    """待办事项更新请求体"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    completed: Optional[bool] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v):
        if v is not None:
            if len(v) == 0:
                raise ValueError("Title cannot be empty")
        return v


class TodoInDB(TodoResponse):
    """数据库内的待办事项模型，包含内部ID"""
    id: int = Field(..., example=1)
    created_at: datetime = Field(..., example="2023-10-01T12:00:00")
    updated_at: datetime = Field(..., example="2023-10-01T12:05:00")


class TodoResponseWithId(TodoResponse):
    """包含ID的响应模型，用于API返回"""
    id: int