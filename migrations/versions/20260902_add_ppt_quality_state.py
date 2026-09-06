"""add persistent PPT outline and quality state"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260902_ppt_quality_state"
down_revision: Union[str, Sequence[str], None] = (
    "20260422_add_file_parse_cache",
    "aicloud001",
    "permission_three_tier",
    "20260829_state_reconciliation",
    "add_files_tasks",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("outline_id", sa.String(length=64), nullable=True))
    op.add_column("tasks", sa.Column("outline_version", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("quality_mode", sa.String(length=20), nullable=True))
    op.add_column("tasks", sa.Column("quality_report_artifact_id", sa.String(length=64), nullable=True))
    op.create_index("idx_tasks_outline_id", "tasks", ["outline_id"])

    op.create_table(
        "ppt_outlines",
        sa.Column("record_id", sa.String(length=64), nullable=False),
        sa.Column("outline_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("scenario", sa.String(length=40), nullable=False),
        sa.Column("template_id", sa.String(length=80), nullable=False),
        sa.Column("slide_limit", sa.Integer(), nullable=False),
        sa.Column("slides_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("record_id"),
        sa.UniqueConstraint("outline_id", "version", name="uq_ppt_outlines_id_version"),
    )
    op.create_index("idx_ppt_outlines_user_status", "ppt_outlines", ["user_id", "status"])

    op.create_table(
        "ppt_quality_reports",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("outline_id", sa.String(length=64), nullable=False),
        sa.Column("outline_version", sa.Integer(), nullable=False),
        sa.Column("quality_mode", sa.String(length=20), nullable=False),
        sa.Column("template_id", sa.String(length=80), nullable=False),
        sa.Column("template_version", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("slide_scores_json", sa.JSON(), nullable=False),
        sa.Column("issues_json", sa.JSON(), nullable=False),
        sa.Column("reflow_attempts_json", sa.JSON(), nullable=False),
        sa.Column("degraded_stage", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.task_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "version", name="uq_ppt_quality_reports_task_version"),
    )
    op.create_index("idx_ppt_quality_reports_outline", "ppt_quality_reports", ["outline_id", "outline_version"])


def downgrade() -> None:
    op.drop_index("idx_ppt_quality_reports_outline", table_name="ppt_quality_reports")
    op.drop_table("ppt_quality_reports")
    op.drop_index("idx_ppt_outlines_user_status", table_name="ppt_outlines")
    op.drop_table("ppt_outlines")
    op.drop_index("idx_tasks_outline_id", table_name="tasks")
    for column in ("quality_report_artifact_id", "quality_mode", "outline_version", "outline_id"):
        op.drop_column("tasks", column)
