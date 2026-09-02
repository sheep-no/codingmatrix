"""add_project_path_to_saved_projects

Revision ID: 20260521_add_project_path
Revises: a1b2c3d4e5f6
Create Date: 2026-05-21

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260521_add_project_path'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'saved_projects',
        sa.Column('project_path', sa.String(500), nullable=True)
    )
    op.create_index(
        'idx_saved_project_path',
        'saved_projects',
        ['project_path'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('idx_saved_project_path', table_name='saved_projects')
    op.drop_column('saved_projects', 'project_path')
