"""Enforce at most one default AI provider, without enabling inference.

Revision ID: 20261104_0010
Revises: 20261104_0009
"""
from alembic import op
import sqlalchemy as sa

revision = '20261104_0010'
down_revision = '20261104_0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('ai_providers', sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_check_constraint('ck_ai_provider_default_active', 'ai_providers', 'NOT (archived AND is_default)')
    op.create_index('uq_ai_providers_single_default', 'ai_providers', ['is_default'], unique=True,
                    postgresql_where=sa.text('is_default IS TRUE'))


def downgrade() -> None:
    raise RuntimeError('Forward-only migration: provider configuration must be preserved')
