"""add performance indexes

Revision ID: a1b2c3d4e5f6
Revises: 56882bedb846
Create Date: 2026-04-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '56882bedb846'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """添加性能优化索引"""
    
    # 用户表索引
    op.create_index(
        'ix_user_email',
        'user',
        ['email'],
        unique=False
    )
    op.create_index(
        'ix_user_created_at',
        'user',
        ['created_at'],
        unique=False
    )
    
    # 历史记录表索引（优化搜索和分页）
    op.create_index(
        'ix_history_user_conversation',
        'history',
        ['user_id', 'conversation_id'],
        unique=False
    )
    op.create_index(
        'ix_history_created_at_desc',
        'history',
        [sa.text('created_at DESC')],
        unique=False
    )
    op.create_index(
        'ix_history_response',
        'history',
        ['response'],
        unique=False
    )
    
    # 聊天历史表索引（优化对话加载）
    op.create_index(
        'ix_chat_history_user_created',
        'chat_history',
        ['user_id', 'created_at'],
        unique=False
    )
    op.create_index(
        'ix_chat_history_user_archived',
        'chat_history',
        ['user_id', 'is_archived'],
        unique=False
    )
    
    # 权限表索引
    op.create_index(
        'ix_permission_user_id',
        'permission',
        ['user_id'],
        unique=True
    )


def downgrade() -> None:
    """删除索引"""
    op.drop_index('ix_permission_user_id', table_name='permission')
    op.drop_index('ix_chat_history_user_archived', table_name='chat_history')
    op.drop_index('ix_chat_history_user_created', table_name='chat_history')
    op.drop_index('ix_history_response', table_name='history')
    op.drop_index('ix_history_created_at_desc', table_name='history')
    op.drop_index('ix_history_user_conversation', table_name='history')
    op.drop_index('ix_user_created_at', table_name='user')
    op.drop_index('ix_user_email', table_name='user')
