"""add GirlAI companion memory consent fields"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260904_girlai_memory_consent"
down_revision: Union[str, Sequence[str], None] = "20260902_ppt_quality_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="confirmed"),
    )
    op.add_column(
        "user_preferences",
        sa.Column("consent_source", sa.String(length=30), nullable=False, server_default="system_derived"),
    )
    op.add_column(
        "user_preferences",
        sa.Column("visibility", sa.String(length=30), nullable=False, server_default="companion_allowed"),
    )
    op.add_column("user_preferences", sa.Column("last_used_at", sa.DateTime(), nullable=True))
    op.create_index(
        "idx_user_preferences_user_status_visibility",
        "user_preferences",
        ["user_id", "status", "visibility"],
    )


def downgrade() -> None:
    op.drop_index("idx_user_preferences_user_status_visibility", table_name="user_preferences")
    for column in ("last_used_at", "visibility", "consent_source", "status"):
        op.drop_column("user_preferences", column)
