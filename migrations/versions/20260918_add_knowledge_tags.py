"""add tags column to knowledge_entries

Revision ID: 20260918_add_knowledge_tags
Revises: 20260918_merge_agent_heads
Create Date: 2026-09-18

KnowledgeRequest and KnowledgeResponse already carried a tags field, and the
endpoint passed it into AgentMemoryService, but neither the model nor the table
had a tags column. Existing tables need the column added explicitly because
create_all does not evolve them.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260918_add_knowledge_tags"
down_revision: Union[str, Sequence[str], None] = "20260918_merge_agent_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("knowledge_entries")}
    if "tags" not in columns:
        op.add_column("knowledge_entries", sa.Column("tags", sa.JSON(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("knowledge_entries")}
    if "tags" in columns:
        op.drop_column("knowledge_entries", "tags")
