"""Step 7B: Owner posting schedules and scheduled posts (Facebook Page).

Forward-only. Nothing posts unless the Owner turns a schedule on.

Revision ID: 20261108_0026
Revises: 20261108_0025
"""
from alembic import op
import sqlalchemy as sa

revision = '20261108_0026'
down_revision = '20261108_0025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'posting_schedules',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('campaign_id', sa.Uuid(), sa.ForeignKey('campaigns.id', ondelete='RESTRICT'), nullable=False, unique=True),
        sa.Column('integration_id', sa.Uuid(), sa.ForeignKey('integrations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('posts_per_day', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('hours', sa.JSON(), nullable=False),
        sa.Column('paused_reason', sa.String(300)),
        sa.Column('updated_by', sa.String(100), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('posts_per_day >= 1 AND posts_per_day <= 6', name='ck_posting_schedule_per_day'),
    )
    op.create_table(
        'scheduled_posts',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('campaign_id', sa.Uuid(), sa.ForeignKey('campaigns.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('content_id', sa.Uuid(), sa.ForeignKey('content_items.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('version_no', sa.Integer(), nullable=False),
        sa.Column('integration_id', sa.Uuid(), sa.ForeignKey('integrations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('slot_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='QUEUED'),
        sa.Column('attempted_at', sa.DateTime(timezone=True)),
        sa.Column('external_post_id', sa.String(100)),
        sa.Column('error', sa.String(300)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('QUEUED','POSTING','POSTED','FAILED','CANCELLED')", name='ck_scheduled_post_status'),
        sa.CheckConstraint("(status = 'POSTED') = (external_post_id IS NOT NULL)", name='ck_scheduled_post_posted'),
    )
    op.create_index('uq_scheduled_post_active', 'scheduled_posts', ['content_id'], unique=True, postgresql_where=sa.text("status IN ('QUEUED','POSTING','POSTED')"))
    op.create_index('ix_scheduled_posts_due', 'scheduled_posts', ['status', 'slot_at'])


def downgrade() -> None:
    raise RuntimeError('Forward-only migration: posting history must be preserved')
