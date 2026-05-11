from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from typing import Optional, List
from datetime import datetime

class BaseModel:
    """基础模型类，包含通用字段"""
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class User(BaseModel):
    """用户模型"""
    __tablename__ = 'users'
    
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    email = Column(String(100), unique=True, nullable=True)
    todos = relationship('Todo', back_populates='user', cascade='all, delete-orphan')

class Todo(BaseModel):
    """待办事项模型"""
    __tablename__ = 'todos'
    
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    title = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String(10), default='medium')
    due_date = Column(DateTime, nullable=True)
    completed = Column(Boolean, default=False)
    
    user = relationship('User', back_populates='todos')
    
    @property
    def priority_display(self) -> str:
        """返回优先级的显示文本"""
        priority_map = {
            'low': '低',
            'medium': '中',
            'high': '高'
        }
        return priority_map.get(self.priority, self.priority)
    
    @property
    def status_display(self) -> str:
        """返回完成状态的显示文本"""
        status_map = {
            False: '未完成',
            True: '已完成'
        }
        return status_map.get(self.completed, str(self.completed))
    
    def to_dict(self) -> dict:
        """将模型转换为字典"""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'priority': self.priority,
            'priority_display': self.priority_display,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'completed': self.completed,
            'status_display': self.status_display,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }