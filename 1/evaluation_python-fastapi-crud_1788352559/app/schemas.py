from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from app.models import Record, User


class IncomeType(str, Enum):
    SALARY = "工资"
    INVESTMENT = "投资"
    SIDE_HOBBY = "副业"
    OTHER = "其他"


class ExpenseType(str, Enum):
    FOOD = "餐饮"
    TRANSPORT = "交通"
    HOUSING = "住房"
    HEALTHCARE = "医疗"
    EDUCATION = "教育"
    ENTERTAINMENT = "娱乐"
    OTHER = "其他"


class CategoryType(str, Enum):
    INCOME = "收入"
    EXPENSE = "支出"


class NoteType(str, Enum):
    INFO = "信息"
    REMINDER = "提醒"
    THOUGHT = "想法"


class RecordCreate(BaseModel):
    """记录创建请求体"""
    user: str = Field(..., description="用户标识")
    date: datetime = Field(..., description="日期")
    category: str = Field(..., description="分类")
    amount: float = Field(..., description="金额")
    income: Optional[float] = None
    expense: Optional[float] = None
    note: Optional[str] = Field(None, description="备注")

    class Config:
        schema_extra = {
            "example": {
                "user": "user1",
                "date": "2023-10-01T10:00:00",
                "category": "工资",
                "amount": 5000.0,
                "income": 5000.0,
                "expense": None,
                "note": "工资收入"
            }
        }


class RecordUpdate(BaseModel):
    """记录更新请求体"""
    user: Optional[str] = None
    date: Optional[datetime] = None
    category: Optional[str] = None
    amount: Optional[float] = None
    income: Optional[float] = None
    expense: Optional[float] = None
    note: Optional[str] = None


class RecordResponse(BaseModel):
    """记录响应体"""
    id: int
    user: str
    date: datetime
    income: Optional[float]
    expense: Optional[float]
    category: str
    amount: float
    note: Optional[str]

    class Config:
        from_attributes = True


class RecordListResponse(BaseModel):
    """记录列表响应体"""
    records: List[RecordResponse]
    total: int


class UserCreate(BaseModel):
    """用户创建请求体"""
    username: str = Field(..., description="用户名", min_length=3, max_length=50)
    email: EmailStr = Field(..., description="邮箱地址")


class UserResponse(BaseModel):
    """用户响应体"""
    id: int
    username: str
    email: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """用户列表响应体"""
    users: List[UserResponse]
    total: int


def build_record_schema(record: Dict[str, Any]) -> RecordResponse:
    """
    将字典转换为 RecordResponse 对象，处理 None 值以确保 Schema 完整性
    """
    return RecordResponse(
        id=record['id'],
        user=record['user'],
        date=record['date'],
        income=record.get('income'),
        expense=record.get('expense'),
        category=record['category'],
        amount=record['amount'],
        note=record.get('note')
    )


def build_user_schema(user: Dict[str, Any]) -> UserResponse:
    """
    将字典转换为 UserResponse 对象，处理 None 值以确保 Schema 完整性
    """
    return UserResponse(
        id=user['id'],
        username=user['username'],
        email=user['email'],
        created_at=user['created_at'],
        updated_at=user['updated_at']
    )