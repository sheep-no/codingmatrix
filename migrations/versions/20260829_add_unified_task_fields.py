"""add unified task state fields"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260829_unified_task_fields"
down_revision: Union[str, Sequence[str], None] = "20260829_state_migration_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("session_id", sa.String(length=64), nullable=True))
    op.add_column("tasks", sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tasks", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.add_column("tasks", sa.Column("stage", sa.String(length=80), nullable=True))
    op.add_column("tasks", sa.Column("lease_until", sa.DateTime(), nullable=True))
    op.add_column("tasks", sa.Column("error_json", sa.JSON(), nullable=True))
    op.add_column("tasks", sa.Column("result_json", sa.JSON(), nullable=True))
    op.add_column("tasks", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("tasks", sa.Column("finished_at", sa.DateTime(), nullable=True))
    op.create_index("idx_tasks_session_id", "tasks", ["session_id"])
    op.create_index("idx_task_idempotency", "tasks", ["user_id", "idempotency_key"])
    op.create_foreign_key("fk_tasks_session_id", "tasks", "sessions", ["session_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_tasks_session_id", "tasks", type_="foreignkey")
    op.drop_index("idx_task_idempotency", table_name="tasks")
    op.drop_index("idx_tasks_session_id", table_name="tasks")
    for column_name in (
        "finished_at", "updated_at", "result_json", "error_json", "lease_until",
        "stage", "idempotency_key", "revision", "session_id",
    ):
        op.drop_column("tasks", column_name)
