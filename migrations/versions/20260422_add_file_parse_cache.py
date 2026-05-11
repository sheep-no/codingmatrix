"""
添加文件解析缓存字段

Revision ID: 20260422_add_file_parse_cache
Revises: initial
Create Date: 2026-04-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260422_add_file_parse_cache'
down_revision = 'a1b2c3d4e5f6'  # 链接到最新的迁移
branch_labels = None
depends_on = None


def upgrade() -> None:
    """添加文件解析缓存字段"""
    
    with op.batch_alter_table('files', schema=None) as batch_op:
        # 添加解析内容字段
        batch_op.add_column(sa.Column('parsed_content', sa.Text(), nullable=True))
        
        # 添加解析时间字段
        batch_op.add_column(sa.Column('parsed_at', sa.DateTime(), nullable=True))
        
        # 添加缓存过期时间字段
        batch_op.add_column(sa.Column('cache_expire_at', sa.DateTime(), nullable=True))
    
    # 为已存在的记录设置默认值（可选）
    # 这里不做数据迁移，让新上传的文件自然填充这些字段


def downgrade() -> None:
    """回滚迁移"""
    
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.drop_column('cache_expire_at')
        batch_op.drop_column('parsed_at')
        batch_op.drop_column('parsed_content')
