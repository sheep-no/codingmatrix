from app.models.base import Base
from app.models.unified_state import Artifact, Checkpoint, Message, Session, TaskEvent


def test_unified_state_tables_and_constraints_exist():
    tables = Base.metadata.tables

    assert {"sessions", "messages", "task_events", "checkpoints", "artifacts"} <= set(tables)
    assert "uq_messages_session_sequence" in {c.name for c in tables["messages"].constraints}
    assert "uq_task_events_task_sequence" in {c.name for c in tables["task_events"].constraints}
    assert "uq_checkpoints_task_revision" in {c.name for c in tables["checkpoints"].constraints}
    assert "uq_artifacts_task_type_version" in {c.name for c in tables["artifacts"].constraints}


def test_unified_state_models_use_expected_task_payload_fields():
    assert {"task_id", "sequence", "event_type", "payload_json"} <= set(TaskEvent.__table__.columns.keys())
    assert {"task_id", "revision", "step", "state_json"} <= set(Checkpoint.__table__.columns.keys())
    assert {"user_id", "session_id", "artifact_type", "storage_uri"} <= set(Artifact.__table__.columns.keys())
    assert {"session_id", "sequence", "role", "content"} <= set(Message.__table__.columns.keys())
    assert {"id", "user_id", "module", "status"} <= set(Session.__table__.columns.keys())
