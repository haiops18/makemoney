"""Store Owner-configured AI provider metadata and encrypted credentials.

Revision ID: 20261103_0007
Revises: 20261103_0006
"""
from alembic import op
import sqlalchemy as sa

revision = '20261103_0007'
down_revision = '20261103_0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ai_providers',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('name', sa.String(150), nullable=False, unique=True),
        sa.Column('kind', sa.String(30), nullable=False),
        sa.Column('base_url', sa.String(2048)),
        sa.Column('default_model', sa.String(200), nullable=False),
        sa.Column('encrypted_api_key', sa.Text()),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('OPENAI','GEMINI','ANTHROPIC','OPENAI_COMPATIBLE')", name='ck_ai_provider_kind'),
    )
    op.create_index('ix_ai_providers_created_at', 'ai_providers', ['created_at', 'id'])


def downgrade() -> None:
    raise RuntimeError('Forward-only migration: provider history must be preserved')
