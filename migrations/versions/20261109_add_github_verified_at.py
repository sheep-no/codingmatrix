"""Persist the GitHub remote verification timestamp."""
from alembic import op
import sqlalchemy as sa


revision = "20261109_github_verified_at"
down_revision = "20260918_unique_tasks_task_id"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_context().as_sql:
        # 离线（--sql）模式无连接可反射，直接产出 DDL。
        op.add_column(
            "github_user_configs",
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        )
        return
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("github_user_configs")
    }
    if "verified_at" not in columns:
        op.add_column(
            "github_user_configs",
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    raise RuntimeError("保留 GitHub 验证状态；请使用显式数据迁移进行降级")
