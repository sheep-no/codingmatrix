"""add compatibility mappings and retention records for state migration"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260829_state_migration_tables"
down_revision: Union[str, Sequence[str], None] = "20260521_add_project_path"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "state_compatibility_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("module", sa.String(length=50), nullable=False),
        sa.Column("legacy_type", sa.String(length=50), nullable=False),
        sa.Column("legacy_id", sa.String(length=255), nullable=False),
        sa.Column("unified_type", sa.String(length=50), nullable=False),
        sa.Column("unified_id", sa.String(length=64), nullable=False),
        sa.Column("source_table", sa.String(length=100), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "module", "legacy_type", "legacy_id", name="uq_state_compatibility_legacy_scope"),
    )
    op.create_index("idx_state_compatibility_unified", "state_compatibility_mappings", ["unified_type", "unified_id"])
    op.create_index("idx_state_compatibility_user", "state_compatibility_mappings", ["user_id", "module"])

    op.create_table(
        "state_retention_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=False),
        sa.Column("policy_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("eligible_at", sa.DateTime(), nullable=True),
        sa.Column("archive_at", sa.DateTime(), nullable=True),
        sa.Column("cleanup_at", sa.DateTime(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("cleanup_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("cleanup_result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resource_type", "resource_id", "policy_name", name="uq_state_retention_resource_policy"),
    )
    op.create_index("idx_state_retention_due", "state_retention_records", ["status", "eligible_at"])


def downgrade() -> None:
    op.drop_index("idx_state_retention_due", table_name="state_retention_records")
    op.drop_table("state_retention_records")
    op.drop_index("idx_state_compatibility_user", table_name="state_compatibility_mappings")
    op.drop_index("idx_state_compatibility_unified", table_name="state_compatibility_mappings")
    op.drop_table("state_compatibility_mappings")
