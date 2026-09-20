"""store opening hours (open_time/close_time) + device_heartbeats history table

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'd5e6f7a8b9c0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('stores') as b:
        b.add_column(sa.Column('open_time', sa.String(length=5), nullable=True))
        b.add_column(sa.Column('close_time', sa.String(length=5), nullable=True))
    op.create_table(
        'device_heartbeats',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('device_id', sa.Uuid(), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source_status', sa.String(length=16), nullable=False),
        sa.Column('last_frame_age_s', sa.Double(), nullable=True),
        sa.Column('pending_events', sa.Integer(), nullable=False),
        sa.Column('tracking_session_id', sa.Integer(), nullable=False),
        sa.Column('agent_version', sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_device_heartbeats_device_received', 'device_heartbeats', ['device_id', 'received_at'])


def downgrade() -> None:
    op.drop_index('ix_device_heartbeats_device_received', table_name='device_heartbeats')
    op.drop_table('device_heartbeats')
    with op.batch_alter_table('stores') as b:
        b.drop_column('close_time')
        b.drop_column('open_time')
