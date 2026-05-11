"""
AI Cloud 知识库模型

兼容 SQLite 和 MySQL。
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.models.base import Base


class AicloudKnowledgeDoc(Base):
    """知识库文档元数据表"""
    __tablename__ = "aicloud_knowledge_docs"

    id = Column(String(36), primary_key=True, comment="文档 ID (UUID)")
    user_id = Column(Integer, nullable=False, index=True, comment="用户 ID")
    
    filename = Column(String(255), nullable=False, comment="原始文件名")
    file_type = Column(String(50), nullable=True, comment="文件类型")
    file_size = Column(Integer, default=0, comment="文件大小 (bytes)")
    file_path = Column(String(500), nullable=True, comment="文件存储路径")
    
    status = Column(String(20), default="pending", comment="处理状态")
    error_message = Column(Text, nullable=True, comment="错误信息")
    
    chunk_count = Column(Integer, default=0, comment="分块数量")
    chunk_size = Column(Integer, default=500, comment="每块大小")
    chunk_overlap = Column(Integer, default=50, comment="块重叠大小")
    
    description = Column(Text, nullable=True, comment="文档描述")
    tags = Column(String(500), nullable=True, comment="标签")
    
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    chunks = relationship("AicloudKnowledgeChunk", back_populates="doc", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<AicloudKnowledgeDoc(id={self.id}, filename='{self.filename}')>"


class AicloudKnowledgeChunk(Base):
    """知识库文本块表"""
    __tablename__ = "aicloud_knowledge_chunks"
    
    __table_args__ = (
        Index("idx_doc_user", "doc_id", "user_id"),
        Index("idx_user_collection", "user_id", "collection"),
    )

    id = Column(String(36), primary_key=True, comment="块 ID (UUID)")
    doc_id = Column(String(36), ForeignKey("aicloud_knowledge_docs.id", ondelete="CASCADE"), nullable=False, comment="所属文档 ID")
    user_id = Column(Integer, nullable=False, index=True, comment="用户 ID")
    
    content = Column(Text, nullable=False, comment="文本块内容")
    content_hash = Column(String(64), nullable=True, index=True, comment="内容哈希")
    
    embedding = Column(Text, nullable=True, comment="向量表示 (JSON)")
    embedding_model = Column(String(100), nullable=True, comment="Embedding 模型")
    
    chunk_index = Column(Integer, nullable=False, comment="块索引")
    collection = Column(String(100), default="default", comment="知识库集合名称")
    metadata_json = Column(Text, nullable=True, comment="额外元数据")
    
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    doc = relationship("AicloudKnowledgeDoc", back_populates="chunks")

    def __repr__(self):
        return f"<AicloudKnowledgeChunk(id={self.id}, doc_id={self.doc_id}, index={self.chunk_index})>"
