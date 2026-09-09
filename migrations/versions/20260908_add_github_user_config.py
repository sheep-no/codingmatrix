"""Add encrypted user-scoped GitHub configuration."""
from alembic import op
import sqlalchemy as sa

revision = "20260908_github_user_config"
down_revision = "20260904_girlai_turn_fencing"
branch_labels = None
depends_on = None


def upgrade():
    if "github_user_configs" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "github_user_configs",
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), primary_key=True),
            sa.Column("username", sa.String(39), nullable=False),
            sa.Column("encrypted_token", sa.Text(), nullable=False),
            sa.Column("use_github", sa.Boolean(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade():
    raise RuntimeError("保留用户 GitHub 配置；请使用显式数据迁移进行降级")
