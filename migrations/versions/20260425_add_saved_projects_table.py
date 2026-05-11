"""add saved_projects table

Revision ID: saved_project001
Revises: d7e8f9g0h1i2
Create Date: 2026-04-25 09:00:00.000000

添加用户保存项目功能相关表：
- saved_projects: 用户保存的项目（支持项目保存/加载/删除，限制3个项目）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'saved_project001'
down_revision: Union[str, Sequence[str], None] = 'd7e8f9g0h1i2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'saved_projects',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('project_data', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now(), nullable=True),
    )
    op.create_index('idx_user_updated', 'saved_projects', ['user_id', 'updated_at'])
    op.create_index('idx_saved_projects_user_id', 'saved_projects', ['user_id'])


def downgrade() -> None:
    op.drop_index('idx_saved_projects_user_id', table_name='saved_projects')
    op.drop_index('idx_user_updated', table_name='saved_projects')
    op.drop_table('saved_projects')