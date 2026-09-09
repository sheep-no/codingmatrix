"""Persistent PPT outline and quality report models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint

from app.models.base import Base


class PPTOutline(Base):
    __tablename__ = "ppt_outlines"

    record_id = Column(String(64), primary_key=True)
    outline_id = Column(String(64), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="draft", index=True)
    title = Column(String(300), nullable=False)
    scenario = Column(String(40), nullable=False, default="general")
    template_id = Column(String(80), nullable=False, default="modern")
    slide_limit = Column(Integer, nullable=False)
    slides_json = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("outline_id", "version", name="uq_ppt_outlines_id_version"),
        Index("idx_ppt_outlines_user_status", "user_id", "status"),
    )


class PPTQualityReport(Base):
    __tablename__ = "ppt_quality_reports"

    id = Column(String(64), primary_key=True)
    task_id = Column(String(64), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    outline_id = Column(String(64), nullable=False)
    outline_version = Column(Integer, nullable=False)
    quality_mode = Column(String(20), nullable=False)
    template_id = Column(String(80), nullable=False)
    template_version = Column(String(80), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    overall_score = Column(Integer, nullable=False, default=0)
    slide_scores_json = Column(JSON, nullable=False, default=dict)
    issues_json = Column(JSON, nullable=False, default=list)
    reflow_attempts_json = Column(JSON, nullable=False, default=dict)
    degraded_stage = Column(String(80), nullable=True)
    status = Column(String(30), nullable=False, default="completed")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("task_id", "version", name="uq_ppt_quality_reports_task_version"),
        Index("idx_ppt_quality_reports_outline", "outline_id", "outline_version"),
    )
