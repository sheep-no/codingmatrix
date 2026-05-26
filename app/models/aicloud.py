"""
aicloud 数据模型

包含：
- AicloudSession: 会话管理
- AicloudMessage: 消息存储
- AicloudReview: 审查队列
- AicloudAuditLog: 审计日志
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Boolean, Index
from sqlalchemy.orm import relationship
from app.models.base import Base


class AicloudSession(Base):
    """aicloud 会话表"""
    __tablename__ = "aicloud_sessions"

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_active_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    messages = relationship("AicloudMessage", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_user_active", "user_id", "last_active_at"),
    )


class AicloudMessage(Base):
    """aicloud 消息表"""
    __tablename__ = "aicloud_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("aicloud_sessions.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    session = relationship("AicloudSession", back_populates="messages")

    __table_args__ = (
        Index("idx_session_created", "session_id", "created_at"),
    )


class AicloudReview(Base):
    """aicloud 审查队列表"""
    __tablename__ = "aicloud_reviews"

    id = Column(String(36), primary_key=True)
    operation_type = Column(String(20), nullable=False)
    file_path = Column(String(500), nullable=False)
    content = Column(Text)
    status = Column(String(20), default="pending")
    requested_by = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    reviewed_by = Column(Integer, ForeignKey("user.id"))
    ai_filter_passed = Column(Boolean)
    details = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    reviewed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_status_created", "status", "created_at"),
        Index("idx_requested_by", "requested_by"),
    )


class AicloudAuditLog(Base):
    """aicloud 审计日志表"""
    __tablename__ = "aicloud_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    operation = Column(String(50), nullable=False)
    file_path = Column(String(500))
    url = Column(String(1000))
    status = Column(String(20), nullable=False)
    details = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_user_operation", "user_id", "operation"),
        Index("idx_user_created", "user_id", "created_at"),
    )
