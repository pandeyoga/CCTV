"""phase 4: telegram chat per store, alert notification marks, camera snapshot, zones + zone_samples

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'f7a8b9c0d1e2'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('stores') as b:
        b.add_column(sa.Column('telegram_chat_id', sa.String(length=64), nullable=True))
    with op.batch_alter_table('alerts') as b:
        b.add_column(sa.Column('notified_at', sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column('resolved_notified_at', sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table('cameras') as b:
        b.add_column(sa.Column('snapshot_at', sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        'zones',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('store_id', sa.Uuid(), nullable=False),
        sa.Column('camera_id', sa.Uuid(), nullable=False),
        sa.Column('external_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('polygon', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id']),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('camera_id', 'external_id', name='uq_zones_camera_external'),
    )
    op.create_index('ix_zones_tenant_id', 'zones', ['tenant_id'])
    op.create_index('ix_zones_store_id', 'zones', ['store_id'])
    op.create_index('ix_zones_camera_id', 'zones', ['camera_id'])
    op.create_table(
        'zone_samples',
        sa.Column('sample_id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('store_id', sa.Uuid(), nullable=False),
        sa.Column('camera_id', sa.Uuid(), nullable=False),
        sa.Column('zone_id', sa.Uuid(), nullable=False),
        sa.Column('device_id', sa.Uuid(), nullable=False),
        sa.Column('sample_ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('interval_s', sa.Double(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('count_max', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id']),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id']),
        sa.ForeignKeyConstraint(['zone_id'], ['zones.id']),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id']),
        sa.PrimaryKeyConstraint('sample_id'),
    )
    op.create_index('ix_zone_samples_zone_ts', 'zone_samples', ['zone_id', 'sample_ts'])
    op.create_index('ix_zone_samples_store_ts', 'zone_samples', ['store_id', 'sample_ts'])


def downgrade() -> None:
    op.drop_index('ix_zone_samples_store_ts', table_name='zone_samples')
    op.drop_index('ix_zone_samples_zone_ts', table_name='zone_samples')
    op.drop_table('zone_samples')
    op.drop_index('ix_zones_camera_id', table_name='zones')
    op.drop_index('ix_zones_store_id', table_name='zones')
    op.drop_index('ix_zones_tenant_id', table_name='zones')
    op.drop_table('zones')
    with op.batch_alter_table('cameras') as b:
        b.drop_column('snapshot_at')
    with op.batch_alter_table('alerts') as b:
        b.drop_column('resolved_notified_at')
        b.drop_column('notified_at')
    with op.batch_alter_table('stores') as b:
        b.drop_column('telegram_chat_id')
