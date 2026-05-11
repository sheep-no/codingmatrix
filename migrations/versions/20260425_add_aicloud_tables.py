"""add aicloud tables

Revision ID: aicloud001
Revises: d7e8f9g0h1i2
Create Date: 2026-04-25 12:00:00.000000

添加 aicloud 功能相关表：
- aicloud_sessions: 会话管理
- aicloud_messages: 消息存储
- aicloud_reviews: 审查队列
- aicloud_audit_logs: 审计日志
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'aicloud001'
down_revision: Union[str, Sequence[str], None] = 'd7e8f9g0h1i2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'aicloud_sessions',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_active_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('idx_aicloud_user_active', 'aicloud_sessions', ['user_id', 'last_active_at'])
    op.create_index('idx_aicloud_user_id', 'aicloud_sessions', ['user_id'])

    op.create_table(
        'aicloud_messages',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('session_id', sa.String(length=36), sa.ForeignKey('aicloud_sessions.id'), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_aicloud_session_created', 'aicloud_messages', ['session_id', 'created_at'])
    op.create_index('idx_aicloud_session_id', 'aicloud_messages', ['session_id'])

    op.create_table(
        'aicloud_reviews',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('operation_type', sa.String(length=20), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('requested_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('ai_filter_passed', sa.Boolean(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_aicloud_review_status_created', 'aicloud_reviews', ['status', 'created_at'])
    op.create_index('idx_aicloud_review_requested_by', 'aicloud_reviews', ['requested_by'])

    op.create_table(
        'aicloud_audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('operation', sa.String(length=50), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=True),
        sa.Column('url', sa.String(length=1000), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_aicloud_audit_user_operation', 'aicloud_audit_logs', ['user_id', 'operation'])
    op.create_index('idx_aicloud_audit_user_created', 'aicloud_audit_logs', ['user_id', 'created_at'])


def downgrade() -> None:
    op.drop_table('aicloud_audit_logs')
    op.drop_table('aicloud_reviews')
    op.drop_table('aicloud_messages')
    op.drop_table('aicloud_sessions')
