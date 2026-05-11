"""
Agent Memory 数据库模型

存储 Agent 的对话记忆、知识和反思
"""

from sqlalchemy import Column, String, Text, Integer, DateTime, Float, Boolean, Index, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.models.base import Base
import uuid
from datetime import datetime


class AgentSession(Base):
    """Agent 会话"""
    __tablename__ = "agent_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    session_type = Column(String(20), default="general")  # general, react, code, visual
    model_key = Column(String(50), default="deepseek-r1-qwen3-8b")
    context_summary = Column(Text)  # 对话摘要
    total_steps = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    success = Column(Boolean, default=True)
    ended_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="agent_sessions")
    memory_entries = relationship("MemoryEntry", back_populates="session", cascade="all, delete-orphan")
    reflections = relationship("AgentReflection", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_agent_sessions_user_created", "user_id", "created_at"),
    )


class MemoryEntry(Base):
    """记忆条目"""
    __tablename__ = "memory_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("agent_sessions.id"), nullable=False, index=True)
    entry_type = Column(String(20), nullable=False)  # user, assistant, tool, knowledge
    content = Column(Text, nullable=False)
    extra_data = Column(JSON, default=dict)  # 存储额外信息
    embedding = Column(JSON)  # 存储向量嵌入（如果有）
    importance = Column(Float, default=1.0)  # 0.0-1.0
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    session = relationship("AgentSession", back_populates="memory_entries")

    __table_args__ = (
        Index("ix_memory_entries_session_type", "session_id", "entry_type"),
        Index("ix_memory_entries_created", "created_at"),
    )


class AgentReflection(Base):
    """Agent 反思记录"""
    __tablename__ = "agent_reflections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("agent_sessions.id"), nullable=False, index=True)
    task = Column(Text)  # 相关任务
    reflection = Column(Text, nullable=False)  # 反思内容
    insights = Column(JSON, default=list)  # 提取的洞察
    confidence = Column(Float, default=0.5)  # 置信度
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    session = relationship("AgentSession", back_populates="reflections")

    __table_args__ = (
        Index("ix_agent_reflections_session", "session_id", "created_at"),
    )


class KnowledgeEntry(Base):
    """知识条目 - 存储学到的知识"""
    __tablename__ = "knowledge_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    knowledge_key = Column(String(255), index=True)  # 知识关键词
    content = Column(Text, nullable=False)  # 知识内容
    category = Column(String(50), default="general")  # 分类
    source = Column(String(20))  # 来源：user, agent, extracted
    importance = Column(Float, default=0.5)  # 重要性
    usage_count = Column(Integer, default=0)  # 使用次数
    last_used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="knowledge_entries")

    __table_args__ = (
        Index("ix_knowledge_user_category", "user_id", "category"),
        Index("ix_knowledge_importance", "importance"),
    )


class ToolExecutionLog(Base):
    """工具执行日志"""
    __tablename__ = "tool_execution_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("agent_sessions.id"), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False, index=True)
    tool_params = Column(JSON, default=dict)
    tool_result = Column(Text)
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    execution_time = Column(Float)  # 毫秒
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_tool_logs_session_tool", "session_id", "tool_name"),
    )


class ModelUsageStats(Base):
    """模型使用统计"""
    __tablename__ = "model_usage_stats"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    model_key = Column(String(50), nullable=False, index=True)
    model_name = Column(String(100))
    request_count = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    avg_execution_time = Column(Float, default=0)
    last_used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="model_usage_stats")

    __table_args__ = (
        Index("ix_model_stats_user_model", "user_id", "model_key", unique=True),
    )
