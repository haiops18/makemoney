"""Add per-agent AI configuration without authorizing inference.

Revision ID: 20261104_0008
Revises: 20261103_0007
"""
from alembic import op
import sqlalchemy as sa

revision = '20261104_0008'
down_revision = '20261103_0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('ai_agent_profiles',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('agent_id', sa.Uuid(), sa.ForeignKey('agents.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('provider_id', sa.Uuid(), sa.ForeignKey('ai_providers.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('model_id', sa.String(200), nullable=False),
        sa.Column('max_output_tokens', sa.Integer(), nullable=False),
        sa.Column('temperature', sa.Numeric(3, 2)),
        sa.Column('timeout_seconds', sa.Integer(), nullable=False),
        sa.Column('max_cost_usd', sa.Numeric(18, 6), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('agent_id', name='uq_ai_agent_profile_agent'),
        sa.CheckConstraint('max_output_tokens BETWEEN 1 AND 100000', name='ck_ai_profile_tokens'),
        sa.CheckConstraint('timeout_seconds BETWEEN 1 AND 300', name='ck_ai_profile_timeout'),
        sa.CheckConstraint('max_cost_usd > 0 AND max_cost_usd <= 45', name='ck_ai_profile_cost'),
        sa.CheckConstraint('temperature IS NULL OR (temperature >= 0 AND temperature <= 2)', name='ck_ai_profile_temperature'))


def downgrade() -> None:
    raise RuntimeError('Forward-only migration: agent configuration history must be preserved')
