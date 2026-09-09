import importlib.util
from pathlib import Path

from app.models.base import Base
from app.db.models import ProjectSession
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


def test_project_to_dict_exposes_lifecycle_state():
    project = ProjectSession(
        session_id="serialized-project",
        user_id="1",
        requirement="serialize",
        lifecycle_status="archived",
        retention_class="standard",
        pinned=True,
    )

    data = project.to_dict()

    assert data["lifecycle_status"] == "archived"
    assert data["retention_class"] == "standard"
    assert data["pinned"] is True
    assert data["archived_at"] is None
    assert data["purge_after"] is None


def test_project_lifecycle_migration_follows_state_reconciliation():
    migration_path = (
        Path(__file__).parents[2]
        / "migrations"
        / "versions"
        / "20260909_add_project_lifecycle_fields.py"
    )
    spec = importlib.util.spec_from_file_location("project_lifecycle_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "20260909_project_lifecycle_fields"
    assert migration.down_revision == "20260829_state_reconciliation"
    assert {"upgrade", "downgrade"} <= set(vars(migration))
