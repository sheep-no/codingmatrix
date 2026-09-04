"""Unified session, event, checkpoint and artifact persistence models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint

from app.models.base import Base


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    module = Column(String(50), nullable=False, index=True)
    external_id = Column(String(128), nullable=True, index=True)
    title = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_sessions_user_module", "user_id", "module"),
        UniqueConstraint(
            "user_id",
            "module",
            "external_id",
            name="uq_sessions_user_module_external",
        ),
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    role = Column(String(30), nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_messages_session_sequence"),
        Index("idx_messages_session_sequence", "session_id", "sequence"),
    )


class SessionEvent(Base):
    __tablename__ = "session_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    event_type = Column(String(64), nullable=False, index=True)
    turn_id = Column(String(128), nullable=False)
    payload_json = Column(JSON, nullable=False, default=dict)
    schema_version = Column(String(20), nullable=False, default="1")
    reservation_token = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_session_events_session_sequence"),
        UniqueConstraint("session_id", "turn_id", name="uq_session_events_session_turn"),
        Index("idx_session_events_session_sequence", "session_id", "sequence"),
    )


class TaskEvent(Base):
    __tablename__ = "task_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    event_type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=True)
    progress = Column(Integer, nullable=True)
    payload_json = Column(JSON, nullable=False, default=dict)
    schema_version = Column(String(20), nullable=False, default="1")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("task_id", "sequence", name="uq_task_events_task_sequence"),
        Index("idx_task_events_task_sequence", "task_id", "sequence"),
    )


class Checkpoint(Base):
    __tablename__ = "checkpoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    step = Column(String(80), nullable=False)
    state_json = Column(JSON, nullable=False, default=dict)
    input_ref = Column(String(512), nullable=True)
    artifact_ref = Column(String(512), nullable=True)
    schema_version = Column(String(20), nullable=False, default="1")
    idempotency_key = Column(String(128), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("task_id", "revision", name="uq_checkpoints_task_revision"),
        UniqueConstraint("task_id", "idempotency_key", name="uq_checkpoints_task_idempotency"),
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(64), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    task_id = Column(String(64), ForeignKey("tasks.task_id", ondelete="SET NULL"), nullable=True, index=True)
    artifact_type = Column(String(50), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    storage_uri = Column(String(1024), nullable=False)
    content_hash = Column(String(64), nullable=True, index=True)
    parent_artifact_id = Column(String(64), ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    archived_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("task_id", "artifact_type", "version", name="uq_artifacts_task_type_version"),
        Index("idx_artifacts_user_session", "user_id", "session_id"),
    )


class StateCompatibilityMapping(Base):
    __tablename__ = "state_compatibility_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    module = Column(String(50), nullable=False)
    legacy_type = Column(String(50), nullable=False)
    legacy_id = Column(String(255), nullable=False)
    unified_type = Column(String(50), nullable=False)
    unified_id = Column(String(64), nullable=False)
    source_table = Column(String(100), nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "module", "legacy_type", "legacy_id",
            name="uq_state_compatibility_legacy_scope",
        ),
        Index("idx_state_compatibility_unified", "unified_type", "unified_id"),
    )


class StateRetentionRecord(Base):
    __tablename__ = "state_retention_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String(64), nullable=False)
    policy_name = Column(String(100), nullable=False)
    status = Column(String(30), nullable=False, default="eligible", index=True)
    eligible_at = Column(DateTime, nullable=True)
    archive_at = Column(DateTime, nullable=True)
    cleanup_at = Column(DateTime, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    cleanup_idempotency_key = Column(String(128), nullable=True)
    cleanup_result_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", "policy_name", name="uq_state_retention_resource_policy"),
        Index("idx_state_retention_due", "status", "eligible_at"),
    )


class StateReconciliationRecord(Base):
    __tablename__ = "state_reconciliation_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True)
    module = Column(String(50), nullable=False, index=True)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String(64), nullable=False)
    status = Column(String(30), nullable=False, default="open", index=True)
    expected_json = Column(JSON, nullable=False, default=dict)
    actual_json = Column(JSON, nullable=False, default=dict)
    difference_json = Column(JSON, nullable=False, default=dict)
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    next_retry_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("module", "resource_type", "resource_id", name="uq_state_reconciliation_resource"),
        Index("idx_state_reconciliation_retry", "status", "next_retry_at"),
    )
