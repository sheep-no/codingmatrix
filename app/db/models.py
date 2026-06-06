"""工作流历史记录数据库模型"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, BigInteger, Index, UniqueConstraint
from app.models.base import Base


class ProjectSession(Base):
    """项目生成会话表（每用户仅允许一个活跃会话）"""
    __tablename__ = "project_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False)
    user_id = Column(String(100), nullable=False)
    requirement = Column(Text, nullable=False)
    output_dir = Column(String(500), nullable=True)  # 相对路径: {user_id}/{project_name}
    status = Column(String(50), default="running")  # running, completed, failed, cancelled
    memory_usage_mb = Column(Integer, default=0)  # 预估内存占用（MB）
    files_generated = Column(Integer, default=0)
    files_total = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_activity_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)  # 最后一次活动时间
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('ix_user_status', 'user_id', 'status'),  # 加速并发检查
        UniqueConstraint('user_id', 'session_id', name='uq_user_session'),  # 防止同名项目
    )

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "requirement": self.requirement,
            "output_dir": self.output_dir,
            "status": self.status,
            "memory_usage_mb": self.memory_usage_mb,
            "files_generated": self.files_generated,
            "files_total": self.files_total,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class WorkflowHistory(Base):
    """工作流执行历史记录表"""
    __tablename__ = "workflow_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    request = Column(Text, nullable=False)
    task_graph = Column(JSON, nullable=True)
    status = Column(String(50), default="pending")
    nodes_count = Column(Integer, default=0)
    completed_nodes = Column(Integer, default=0)
    result_summary = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "user_id": self.user_id,
            "request": self.request,
            "task_graph": self.task_graph,
            "status": self.status,
            "nodes_count": self.nodes_count,
            "completed_nodes": self.completed_nodes,
            "result_summary": self.result_summary,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ImageGenerationHistory(Base):
    """AI 绘图历史记录表"""
    __tablename__ = "image_generation_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    session_id = Column(String(100), nullable=True, index=True)
    prompt = Column(Text, nullable=False)
    negative_prompt = Column(Text, nullable=True)
    image_urls = Column(JSON, nullable=True)
    generation_type = Column(String(50), default="text-to-image")
    params = Column(JSON, nullable=True)
    seed = Column(Integer, nullable=True)
    status = Column(String(50), default="completed")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "image_id": self.image_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "image_urls": self.image_urls,
            "generation_type": self.generation_type,
            "params": self.params,
            "seed": self.seed,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
