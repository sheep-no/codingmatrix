"""add state reconciliation records"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260829_state_reconciliation"
down_revision: Union[str, Sequence[str], None] = "20260829_unified_task_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "state_reconciliation_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("module", sa.String(length=50), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("expected_json", sa.JSON(), nullable=False),
        sa.Column("actual_json", sa.JSON(), nullable=False),
        sa.Column("difference_json", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("module", "resource_type", "resource_id", name="uq_state_reconciliation_resource"),
    )
    op.create_index("idx_state_reconciliation_module", "state_reconciliation_records", ["module"])
    op.create_index("idx_state_reconciliation_retry", "state_reconciliation_records", ["status", "next_retry_at"])


def downgrade() -> None:
    op.drop_index("idx_state_reconciliation_retry", table_name="state_reconciliation_records")
    op.drop_index("idx_state_reconciliation_module", table_name="state_reconciliation_records")
    op.drop_table("state_reconciliation_records")
