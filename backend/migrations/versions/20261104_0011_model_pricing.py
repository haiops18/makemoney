"""Versioned Owner-entered model prices, never a spend authorization.

Revision ID: 20261104_0011
Revises: 20261104_0010
"""
from alembic import op
import sqlalchemy as sa

revision = '20261104_0011'
down_revision = '20261104_0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('ai_model_prices',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('provider_id', sa.Uuid(), sa.ForeignKey('ai_providers.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('model_id', sa.String(200), nullable=False),
        sa.Column('version', sa.String(100), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False),
        sa.Column('input_per_million', sa.Numeric(18, 6), nullable=False),
        sa.Column('output_per_million', sa.Numeric(18, 6), nullable=False),
        sa.Column('effective_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('source_note', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('provider_id', 'model_id', 'version', name='uq_ai_model_price_version'),
        sa.CheckConstraint("currency = 'USD'", name='ck_ai_model_price_currency'),
        sa.CheckConstraint('input_per_million >= 0 AND output_per_million >= 0', name='ck_ai_model_price_nonnegative'),
        sa.CheckConstraint('expires_at IS NULL OR expires_at > effective_at', name='ck_ai_model_price_period'))
    op.create_index('ix_ai_model_prices_provider_model_effective', 'ai_model_prices', ['provider_id', 'model_id', 'effective_at'])


def downgrade() -> None:
    raise RuntimeError('Forward-only migration: model price history must be preserved')
