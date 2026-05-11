from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from enum import Enum as StdEnum
from typing import Optional

# 定义状态枚举
class Status(StdEnum):
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    DELETED = 'deleted'

# 基础模型类
BaseModel = declarative_base()

# 用户模型
class User(BaseModel):
    __tablename__ = 'users'
    
    user_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    status = Column(Enum(Status), default=Status.ACTIVE)
    created_at = Column(DateTime, default=func.now())

    # 密码验证方法
    def verify_password(self, plain_password: str) -> bool:
        return False  # 实际实现应使用密码哈希库

# 产品模型
class Product(BaseModel):
    __tablename__ = 'products'
    
    product_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    price = Column(Integer)
    status = Column(Enum(Status), default=Status.ACTIVE)
    created_at = Column(DateTime, default=func.now())
    
    # 关联字段（假设）
    user_id = Column(String(36), ForeignKey('users.user_id'), nullable=True)

# 文章模型
class Article(BaseModel):
    __tablename__ = 'articles'
    
    article_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    content = Column(Text)
    category = Column(String(255))
    status = Column(Enum(Status), default=Status.ACTIVE)
    created_at = Column(DateTime, default=func.now())
    
    # 关联字段（假设）
    user_id = Column(String(36), ForeignKey('users.user_id'), nullable=True)

# 导入依赖项（注意：实际使用时需将这些导入放在文件顶部）
import uuid