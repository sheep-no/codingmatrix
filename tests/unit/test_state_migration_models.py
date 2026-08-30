from app.models.base import Base
from app.models.unified_state import StateCompatibilityMapping, StateRetentionRecord


def test_compatibility_mapping_scope_is_unique():
    table = StateCompatibilityMapping.__table__
    assert "uq_state_compatibility_legacy_scope" in {constraint.name for constraint in table.constraints}
    assert {"user_id", "legacy_id", "unified_id"} <= set(table.columns.keys())


def test_retention_record_has_idempotent_resource_policy():
    table = StateRetentionRecord.__table__
    assert "uq_state_retention_resource_policy" in {constraint.name for constraint in table.constraints}
    assert {"eligible_at", "archive_at", "cleanup_at", "attempt_count"} <= set(table.columns.keys())
    assert "state_retention_records" in Base.metadata.tables
