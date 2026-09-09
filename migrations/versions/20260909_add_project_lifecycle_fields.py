"""add project lifecycle and retention fields"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260909_project_lifecycle_fields"
down_revision: Union[str, Sequence[str], None] = "20260829_state_reconciliation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_sessions",
        sa.Column("lifecycle_status", sa.String(length=30), nullable=False, server_default="active"),
    )
    op.add_column(
        "project_sessions",
        sa.Column("retention_class", sa.String(length=30), nullable=False, server_default="standard"),
    )
    op.add_column(
        "project_sessions",
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "project_sessions",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "project_sessions",
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_project_sessions_lifecycle_status",
        "project_sessions",
        ["lifecycle_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_sessions_lifecycle_status", table_name="project_sessions")
    op.drop_column("project_sessions", "purge_after")
    op.drop_column("project_sessions", "archived_at")
    op.drop_column("project_sessions", "pinned")
    op.drop_column("project_sessions", "retention_class")
    op.drop_column("project_sessions", "lifecycle_status")
