"""add GirlAI turn reservation fencing"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260904_girlai_turn_fencing"
down_revision: Union[str, Sequence[str], None] = "20260904_girlai_session_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "session_events",
        sa.Column("reservation_token", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_sessions_user_module_external",
        "sessions",
        ["user_id", "module", "external_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_sessions_user_module_external", table_name="sessions")
    op.drop_column("session_events", "reservation_token")
