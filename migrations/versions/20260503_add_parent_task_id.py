"""add parent_task_id for incremental comparison support

Revision ID: task_parent_id
Revises: task_queue_enhance
Create Date: 2026-05-03 00:00:00.000000

添加父子任务关系字段：
- parent_task_id: 父任务 ID（支持基于现有项目修改的增量对比）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'task_parent_id'
down_revision: Union[str, Sequence[str], None] = 'task_queue_enhance'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('parent_task_id', sa.Integer(), nullable=True))

    op.create_index('idx_parent_task_id', 'tasks', ['parent_task_id'])

    op.create_foreign_key(
        'fk_tasks_parent_task_id',
        'tasks', 'tasks',
        ['parent_task_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_tasks_parent_task_id', 'tasks', type_='foreignkey')
    op.drop_index('idx_parent_task_id', table_name='tasks')
    op.drop_column('tasks', 'parent_task_id')
