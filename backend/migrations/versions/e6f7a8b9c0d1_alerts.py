"""alert rules per store + alerts (incidents) table

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa

revision = 'e6f7a8b9c0d1'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'alert_rules',
        sa.Column('store_id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('heartbeat_lost_min', sa.Integer(), nullable=False),
        sa.Column('camera_down_min', sa.Integer(), nullable=False),
        sa.Column('buffer_pending_threshold', sa.Integer(), nullable=False),
        sa.Column('no_events_min', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('store_id'),
    )
    op.create_index('ix_alert_rules_tenant_id', 'alert_rules', ['tenant_id'])
    op.create_table(
        'alerts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('store_id', sa.Uuid(), nullable=False),
        sa.Column('device_id', sa.Uuid(), nullable=True),
        sa.Column('rule', sa.String(length=32), nullable=False),
        sa.Column('severity', sa.String(length=8), nullable=False),
        sa.Column('message', sa.String(length=256), nullable=False),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id']),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id']),
        sa.ForeignKeyConstraint(['acknowledged_by'], ['dashboard_users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_alerts_tenant_opened', 'alerts', ['tenant_id', 'opened_at'])
    op.create_index('ix_alerts_store_resolved', 'alerts', ['store_id', 'resolved_at'])


def downgrade() -> None:
    op.drop_index('ix_alerts_store_resolved', table_name='alerts')
    op.drop_index('ix_alerts_tenant_opened', table_name='alerts')
    op.drop_table('alerts')
    op.drop_index('ix_alert_rules_tenant_id', table_name='alert_rules')
    op.drop_table('alert_rules')
