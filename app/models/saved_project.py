from sqlalchemy.orm import relationship
from app.models.base import Base
from sqlalchemy.sql import func
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Index


class SavedProject(Base):
    """用户保存的项目"""
    __tablename__ = "saved_projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    project_path = Column(String(500))
    project_data = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="saved_projects")

    __table_args__ = (
        Index('idx_user_updated', 'user_id', 'updated_at'),
    )
