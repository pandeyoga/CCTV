"""dashboard users + tenant memberships, device heartbeat columns, count_events.tracking_session_id

Revision ID: 3b9c2d1e5a70
Revises: 7f0ed43c997e
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa

revision = '3b9c2d1e5a70'
down_revision = '7f0ed43c997e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'dashboard_users',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('email', sa.String(length=254), nullable=False),
        sa.Column('password_hash', sa.String(length=128), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )
    op.create_table(
        'tenant_memberships',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['user_id'], ['dashboard_users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'tenant_id', name='uq_tenant_memberships_user_tenant'),
    )
    op.create_index('ix_tenant_memberships_user_id', 'tenant_memberships', ['user_id'])
    op.create_index('ix_tenant_memberships_tenant_id', 'tenant_memberships', ['tenant_id'])
    with op.batch_alter_table('devices') as b:
        b.add_column(sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column('hb_source_status', sa.String(length=16), nullable=True))
        b.add_column(sa.Column('hb_last_frame_age_s', sa.Double(), nullable=True))
        b.add_column(sa.Column('hb_pending_events', sa.Integer(), nullable=True))
        b.add_column(sa.Column('hb_tracking_session_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('hb_agent_version', sa.String(length=32), nullable=True))
    with op.batch_alter_table('count_events') as b:
        b.add_column(sa.Column('tracking_session_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('count_events') as b:
        b.drop_column('tracking_session_id')
    with op.batch_alter_table('devices') as b:
        for c in ('hb_agent_version', 'hb_tracking_session_id', 'hb_pending_events', 'hb_last_frame_age_s',
                  'hb_source_status', 'last_heartbeat_at'):
            b.drop_column(c)
    op.drop_index('ix_tenant_memberships_tenant_id', table_name='tenant_memberships')
    op.drop_index('ix_tenant_memberships_user_id', table_name='tenant_memberships')
    op.drop_table('tenant_memberships')
    op.drop_table('dashboard_users')
