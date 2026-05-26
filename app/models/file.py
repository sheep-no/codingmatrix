"""
文件管理模型
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, Integer, String, DateTime, BigInteger, ForeignKey, Index, Text
from sqlalchemy.orm import relationship
from app.models.base import Base


class File(Base):
    """
    文件表 - 记录用户上传的文件信息
    """
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # 文件信息
    filename = Column(String(255), nullable=False, index=True)  # 原始文件名
    file_path = Column(String(512), nullable=False)  # 存储路径
    file_size = Column(BigInteger, nullable=False)  # 文件大小（字节）
    content_type = Column(String(100))  # MIME 类型
    
    # 文件哈希（用于去重）
    file_hash = Column(String(64), index=True)  # SHA256
    
    # 用户关联
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # 会话关联（文件属于特定对话上下文）
    conversation_id = Column(Integer, index=True)
    
    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 删除标记（软删除）
    is_deleted = Column(Integer, default=0)  # 0:未删除，1:已删除
    
    # 文件解析缓存
    parsed_content = Column(Text)  # 解析后的文本内容
    parsed_at = Column(DateTime)  # 解析时间
    cache_expire_at = Column(DateTime)  # 缓存过期时间
    
    # 关系
    uploader = relationship("User", backref="uploaded_files")
    tasks = relationship("Task", back_populates="file", foreign_keys="Task.input_file_id")
    
    # 索引
    __table_args__ = (
        Index('idx_file_user_created', 'user_id', 'created_at'),
        Index('idx_hash_user', 'file_hash', 'user_id'),
    )
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "filename": self.filename,
            "file_size": self.file_size,
            "content_type": self.content_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "download_url": f"/api/v1/files/{self.id}/download",
            "parsed_content": self.parsed_content,
            "has_cached_parse": self.parsed_content is not None and self.cache_expire_at and self.cache_expire_at > datetime.utcnow()
        }
    
    def is_parse_cache_valid(self, ttl_seconds: int = 3600) -> bool:
        """
        检查解析缓存是否有效
        
        Args:
            ttl_seconds: 缓存 TTL（秒），默认 1 小时
            
        Returns:
            bool: 缓存是否有效
        """
        if not self.parsed_content or not self.parsed_at:
            return False
        
        # 检查是否过期
        if self.cache_expire_at and self.cache_expire_at < datetime.utcnow():
            return False
        
        # 检查是否在 TTL 内
        expire_time = self.parsed_at + timedelta(seconds=ttl_seconds)
        return datetime.utcnow() < expire_time
    
    def update_parse_cache(self, content: str, ttl_seconds: int = 3600):
        """
        更新解析缓存
        
        Args:
            content: 解析后的文本内容
            ttl_seconds: 缓存 TTL（秒），默认 1 小时
        """
        self.parsed_content = content
        self.parsed_at = datetime.utcnow()
        self.cache_expire_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
