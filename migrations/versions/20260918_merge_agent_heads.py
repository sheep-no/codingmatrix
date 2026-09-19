"""merge agent orchestration heads

Revision ID: 20260918_merge_agent_heads
Revises: 20260908_github_user_config, 20260909_project_lifecycle_fields
Create Date: 2026-09-18

The task and project-lifecycle branches both descend from
20260829_state_reconciliation, which left the migration chain with two heads.
This empty merge revision gives the agent memory and task identity fixes a
single parent to hang from.
"""

from typing import Sequence, Union


revision: str = "20260918_merge_agent_heads"
down_revision: Union[str, Sequence[str], None] = (
    "20260908_github_user_config",
    "20260909_project_lifecycle_fields",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
