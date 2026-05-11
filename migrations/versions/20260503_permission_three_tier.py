"""upgrade permission levels to three-tier (normal/admin/superadmin)

Revision ID: permission_three_tier
Revises: task_parent_id
Create Date: 2026-05-03 00:00:00.000000

将权限级别从两种扩展到三种：
- normal: 普通用户
- admin: 管理员（新增）
- superadmin: 超级管理员（原 super 升级）

现有 super 权限用户自动升级为 superadmin
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'permission_three_tier'
down_revision: Union[str, Sequence[str], None] = 'task_parent_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 将现有的 'super' 权限升级为 'superadmin'
    op.execute(
        "UPDATE permission SET permission_level = 'superadmin' WHERE permission_level = 'super'"
    )


def downgrade() -> None:
    # 回滚时将 'superadmin' 恢复为 'super'
    op.execute(
        "UPDATE permission SET permission_level = 'super' WHERE permission_level = 'superadmin'"
    )
    # 将 'admin' 降级为 'normal'
    op.execute(
        "UPDATE permission SET permission_level = 'normal' WHERE permission_level = 'admin'"
    )
