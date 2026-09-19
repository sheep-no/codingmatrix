"""deduplicate tasks.task_id and enforce uniqueness

Revision ID: 20260918_unique_tasks_task_id
Revises: 20260918_add_knowledge_tags
Create Date: 2026-09-18

Task.task_id declares unique=True, index=True, but databases initialised through
Base.metadata.create_all kept a non-unique column. SQLite resolves
ForeignKey("tasks.task_id") against a unique index, so checkpoints, task_events,
artifacts and ppt_quality_reports failed with "foreign key mismatch" whenever
persist_agent_state wrote a checkpoint.

Duplicate task_id rows have no owner recorded on the child tables, so the
smallest id is kept as canonical and the remaining rows are renamed in place.
No rows are deleted.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260918_unique_tasks_task_id"
down_revision: Union[str, Sequence[str], None] = "20260918_add_knowledge_tags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "ix_tasks_task_id"


def _deduplicate_task_ids(connection) -> None:
    duplicate_task_ids = [
        row[0]
        for row in connection.execute(
            sa.text("SELECT task_id FROM tasks GROUP BY task_id HAVING COUNT(*) > 1")
        )
    ]
    for task_id in duplicate_task_ids:
        row_ids = [
            row[0]
            for row in connection.execute(
                sa.text("SELECT id FROM tasks WHERE task_id = :task_id ORDER BY id"),
                {"task_id": task_id},
            )
        ]
        for row_id in row_ids[1:]:
            # Keep the smallest id canonical. The row_id suffix keeps the new
            # value unique, and the slice keeps it within VARCHAR(64).
            new_task_id = f"{task_id[:48]}__dup{row_id}"
            connection.execute(
                sa.text("UPDATE tasks SET task_id = :new_task_id WHERE id = :row_id"),
                {"new_task_id": new_task_id, "row_id": row_id},
            )


def upgrade() -> None:
    connection = op.get_bind()
    _deduplicate_task_ids(connection)

    inspector = sa.inspect(connection)
    indexes = {index["name"]: index for index in inspector.get_indexes("tasks")}
    existing = indexes.get(_INDEX_NAME)
    if existing is None:
        op.create_index(_INDEX_NAME, "tasks", ["task_id"], unique=True)
    elif not existing.get("unique"):
        op.drop_index(_INDEX_NAME, table_name="tasks")
        op.create_index(_INDEX_NAME, "tasks", ["task_id"], unique=True)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("tasks")}
    if _INDEX_NAME in indexes:
        op.drop_index(_INDEX_NAME, table_name="tasks")
