from sqlalchemy.orm import relationship

from app.models.base import Base
from sqlalchemy.sql import func
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index, Text

class History(Base):
    __tablename__ = "history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    conversation_id = Column(Integer, nullable=False, index=True)
    # 核心：分开存储 prompt 和 response
    prompt = Column(Text, nullable=False)  # 用户的输入
    response = Column(Text, nullable=False)  # AI 的回答
    thinking = Column(Text)
    title = Column(String(200))  # 从 prompt 生成摘要
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 会话元数据（存储图片/文件解析结果、压缩历史等）
    metadata_json = Column(Text)  # JSON 格式的元数据

    __table_args__ = (
        Index('idx_user_conversation', 'user_id', 'conversation_id'),
        Index('idx_user_latest', 'user_id', id.desc()),
    )

    user = relationship("User", back_populates="histories")