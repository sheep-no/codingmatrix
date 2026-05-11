"""create files and tasks tables

Revision ID: add_files_tasks
Revises: 
Create Date: 2024-01-XX

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_files_tasks'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 files 表
    op.create_table('files',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('file_hash', sa.String(length=64), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('is_deleted', sa.Integer(), default=0),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建 files 表索引
    op.create_index('ix_files_id', 'files', ['id'], unique=False)
    op.create_index('ix_files_filename', 'files', ['filename'], unique=False)
    op.create_index('ix_files_file_hash', 'files', ['file_hash'], unique=False)
    op.create_index('ix_files_user_id', 'files', ['user_id'], unique=False)
    op.create_index('idx_user_created', 'files', ['user_id', 'created_at'], unique=False)
    op.create_index('idx_hash_user', 'files', ['file_hash', 'user_id'], unique=False)
    
    # 创建 tasks 表
    op.create_table('tasks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_id', sa.String(length=64), nullable=False),
        sa.Column('task_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('input_file_id', sa.Integer(), nullable=True),
        sa.Column('params', sa.JSON(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('progress', sa.Integer(), default=0),
        sa.Column('progress_message', sa.String(length=255), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('retry_count', sa.Integer(), default=0),
        sa.Column('max_retries', sa.Integer(), default=3),
        sa.Column('worker_id', sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建 tasks 表索引
    op.create_index('ix_tasks_task_id', 'tasks', ['task_id'], unique=True)
    op.create_index('ix_tasks_id', 'tasks', ['id'], unique=False)
    op.create_index('ix_tasks_task_type', 'tasks', ['task_type'], unique=False)
    op.create_index('ix_tasks_status', 'tasks', ['status'], unique=False)
    op.create_index('ix_tasks_user_id', 'tasks', ['user_id'], unique=False)
    op.create_index('idx_user_status', 'tasks', ['user_id', 'status'], unique=False)
    op.create_index('idx_created_status', 'tasks', ['created_at', 'status'], unique=False)


def downgrade() -> None:
    # 删除表（先删除 tasks，再删除 files）
    op.drop_table('tasks')
    op.drop_table('files')
