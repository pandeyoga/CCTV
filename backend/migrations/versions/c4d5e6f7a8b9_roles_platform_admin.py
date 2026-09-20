"""platform admin flag on dashboard_users; membership role vocabulary owner|staff (viewer -> staff)

Revision ID: c4d5e6f7a8b9
Revises: 3b9c2d1e5a70
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa

revision = 'c4d5e6f7a8b9'
down_revision = '3b9c2d1e5a70'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('dashboard_users') as b:
        b.add_column(sa.Column('is_platform_admin', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE tenant_memberships SET role = 'staff' WHERE role = 'viewer'")


def downgrade() -> None:
    op.execute("UPDATE tenant_memberships SET role = 'viewer' WHERE role = 'staff'")
    with op.batch_alter_table('dashboard_users') as b:
        b.drop_column('is_platform_admin')
