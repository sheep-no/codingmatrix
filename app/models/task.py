"""
任务队列模型
"""
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship
from app.models.base import Base


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"       # 等待中
    RUNNING = "running"       # 运行中
    SUCCESS = "success"       # 成功
    FAILED = "failed"         # 失败
    CANCELLED = "cancelled"   # 已取消


class TaskType(str, Enum):
    """任务类型枚举"""
    PROJECT_GENERATE = "project_generate"  # 项目生成
    CODE_GENERATE = "code_generate"        # 代码生成
    PPT_GENERATE = "ppt_generate"          # PPT 生成
    FILE_PROCESS = "file_process"          # 文件处理


class TaskPriority(str, Enum):
    """任务优先级枚举"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Task(Base):
    """
    任务表 - 记录异步任务执行状态
    """
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 任务标识
    task_id = Column(String(64), unique=True, nullable=False, index=True)
    session_id = Column(String(64), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    revision = Column(Integer, default=0, nullable=False)
    idempotency_key = Column(String(128), nullable=True, index=True)

    # Celery 集成
    celery_task_id = Column(String(64), nullable=True, index=True)

    # 任务类型
    task_type = Column(String(50), nullable=False, index=True)

    # 任务状态
    status = Column(String(20), default=TaskStatus.PENDING.value, nullable=False, index=True)
    stage = Column(String(80), nullable=True)
    lease_until = Column(DateTime, nullable=True)

    # 任务优先级 (1-10, 10 is highest)
    priority = Column(Integer, default=5)

    # 超时设置 (秒)
    timeout = Column(Integer, default=300)

    # 任务参数
    input_file_id = Column(Integer, ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    params = Column(JSON, default=dict)

    # 任务结果
    result = Column(JSON, default=dict)
    error_message = Column(Text)
    error_json = Column(JSON, default=dict)
    result_json = Column(JSON, default=dict)

    # 进度信息
    progress = Column(Integer, default=0)
    progress_message = Column(String(255))

    # 用户关联
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)

    # 父子任务关系（支持基于现有项目修改的增量对比）
    parent_task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    # 执行信息
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    worker_id = Column(String(50))

    # 关系
    user = relationship("User", backref="tasks")
    file = relationship("File", back_populates="tasks", foreign_keys=[input_file_id])
    parent_task = relationship("Task", remote_side=[id], backref="child_tasks")

    # 索引
    __table_args__ = (
        Index('idx_user_status_priority', 'user_id', 'status', 'priority'),
        Index('idx_task_status_created', 'status', 'created_at'),
        Index('idx_celery_task_id', 'celery_task_id'),
        Index('idx_parent_task_id', 'parent_task_id'),
        Index('idx_task_idempotency', 'user_id', 'idempotency_key'),
    )

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "celery_task_id": self.celery_task_id,
            "task_type": self.task_type,
            "status": self.status,
            "priority": self.priority,
            "timeout": self.timeout,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "result": self.result,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "parent_task_id": self.parent_task_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
