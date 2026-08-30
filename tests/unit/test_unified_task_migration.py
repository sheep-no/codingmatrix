from pathlib import Path


def test_unified_task_migration_declares_expected_revision_chain():
    migration = Path("migrations/versions/20260829_add_unified_task_fields.py").read_text()
    assert 'revision: str = "20260829_unified_task_fields"' in migration
    assert 'down_revision: Union[str, Sequence[str], None] = "20260829_state_migration_tables"' in migration
    for field in ("session_id", "revision", "idempotency_key", "stage", "lease_until", "error_json", "result_json"):
        assert f'"{field}"' in migration
