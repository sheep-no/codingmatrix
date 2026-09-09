# app/models/chat_history.py
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Index, Boolean, CHAR
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.models.base import Base
import uuid
from datetime import datetime
from app.agent.models import DEFAULT_REASONING_MODEL


class ChatHistory(Base):
    __tablename__ = "chat_histories"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    model = Column(String(100))
    token_usage = Column(Integer, default=0)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="chat_histories")


class ChatSummary(Base):
    """存储超过3天的对话摘要"""
    __tablename__ = "chat_summaries"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    summary_text = Column(Text, nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False, index=True)
    end_date = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="chat_summaries")


class CustomCharacter(Base):
    """用户自定义角色"""
    __tablename__ = "custom_characters"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    name = Column(String(50), nullable=False)
    description = Column(String(200), default="")
    personality = Column(String(200), default="")
    speaking_style = Column(String(200), default="")
    greetings = Column(Text, default="[]")  # JSON array of greeting strings
    tags = Column(Text, default="[]")  # JSON array of tag strings
    model = Column(String(100), default=DEFAULT_REASONING_MODEL)
    temperature = Column(Integer, default=80)  # stored as int (0.8 * 100)
    max_tokens = Column(Integer, default=180)
    avatar_color = Column(String(20), default="#667eea")  # hex color for avatar
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User")


class UserPreference(Base):
    """用户偏好记忆（从对话中提取）"""
    __tablename__ = "user_preferences"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    preference_key = Column(String(50), nullable=False)  # e.g., "name", "hobby", "mood"
    preference_value = Column(Text, nullable=False)
    confidence = Column(Integer, default=80)  # 0-100
    source = Column(String(20), default="extracted")  # "extracted" or "manual"
    status = Column(String(20), nullable=False, default="confirmed", index=True)
    consent_source = Column(String(30), nullable=False, default="system_derived")
    visibility = Column(String(30), nullable=False, default="companion_allowed", index=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User")

    __table_args__ = (
        Index("idx_user_preferences_user_status_visibility", "user_id", "status", "visibility"),
    )
