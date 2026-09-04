"""add GirlAI companion session events"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260904_girlai_session_events"
down_revision: Union[str, Sequence[str], None] = "20260904_girlai_memory_consent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "session_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("turn_id", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "sequence", name="uq_session_events_session_sequence"),
        sa.UniqueConstraint("session_id", "turn_id", name="uq_session_events_session_turn"),
    )
    op.create_index(
        "idx_session_events_session_sequence",
        "session_events",
        ["session_id", "sequence"],
    )
    op.create_index("idx_session_events_event_type", "session_events", ["event_type"])
    op.create_index("idx_session_events_session_id", "session_events", ["session_id"])
    op.create_index("idx_session_events_user_id", "session_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_session_events_user_id", table_name="session_events")
    op.drop_index("idx_session_events_session_id", table_name="session_events")
    op.drop_index("idx_session_events_event_type", table_name="session_events")
    op.drop_index("idx_session_events_session_sequence", table_name="session_events")
    op.drop_table("session_events")
