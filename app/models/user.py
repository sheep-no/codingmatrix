from sqlalchemy.orm import relationship

from app.models.base import Base
from sqlalchemy.sql import func
from sqlalchemy import Column, String, Integer, DateTime

from app.models.saved_project import SavedProject


class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    histories = relationship("History", back_populates="user", order_by="History.id.desc()")
    chat_histories = relationship(
        "ChatHistory",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    chat_summaries = relationship(
        "ChatSummary",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    permission=relationship(
        "Permission",
        back_populates="user",
        uselist=False,
        cascade="all,delete-orphan"
    )
    saved_projects = relationship(
        "SavedProject",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="SavedProject.updated_at.desc()"
    )
    agent_sessions = relationship(
        "AgentSession",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="AgentSession.created_at.desc()"
    )
    knowledge_entries = relationship(
        "KnowledgeEntry",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="KnowledgeEntry.updated_at.desc()"
    )
    model_usage_stats = relationship(
        "ModelUsageStats",
        back_populates="user",
        cascade="all, delete-orphan"
    )