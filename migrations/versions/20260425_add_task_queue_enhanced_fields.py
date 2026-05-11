"""add task queue enhanced fields

Revision ID: task_queue_enhance
Revises: saved_project001
Create Date: 2026-04-25 12:00:00.000000

添加任务队列增强功能相关字段：
- celery_task_id: Celery 任务 ID
- priority: 任务优先级
- timeout: 任务超时时间
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'task_queue_enhance'
down_revision: Union[str, Sequence[str], None] = 'saved_project001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('celery_task_id', sa.String(length=64), nullable=True))
    op.add_column('tasks', sa.Column('priority', sa.Integer(), nullable=False, server_default='5'))
    op.add_column('tasks', sa.Column('timeout', sa.Integer(), nullable=False, server_default='300'))

    op.create_index('idx_celery_task_id', 'tasks', ['celery_task_id'])
    op.create_index('idx_user_status_priority', 'tasks', ['user_id', 'status', 'priority'])
    op.create_index('idx_status_created', 'tasks', ['status', 'created_at'])


def downgrade() -> None:
    op.drop_index('idx_status_created', table_name='tasks')
    op.drop_index('idx_user_status_priority', table_name='tasks')
    op.drop_index('idx_celery_task_id', table_name='tasks')

    op.drop_column('tasks', 'timeout')
    op.drop_column('tasks', 'priority')
    op.drop_column('tasks', 'celery_task_id')