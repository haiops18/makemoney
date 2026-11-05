"""Retain validated outcomes independently of worker leases.

Revision ID: 20261105_0017
Revises: 20261105_0016
"""
from alembic import op
import sqlalchemy as sa

revision = '20261105_0017'
down_revision = '20261105_0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('ai_invocations', sa.Column('output_json', sa.JSON()))
    # Provider model identifiers are configured with the same 200-character
    # contract as profiles; usage must not truncate their accounting identity.
    op.alter_column('usage_records', 'model', type_=sa.String(200), existing_type=sa.String(100))


def downgrade() -> None:
    raise RuntimeError('Forward-only migration: preserve billing outcomes')
