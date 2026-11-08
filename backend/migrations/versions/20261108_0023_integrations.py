"""Step 7B: Owner integrations (search, ACCESSTRADE, Facebook Page) with encrypted secrets.

Forward-only. Creating an integration performs no request.

Revision ID: 20261108_0023
Revises: 20261107_0022
"""
from alembic import op
import sqlalchemy as sa

revision = '20261108_0023'
down_revision = '20261107_0022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'integrations',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('kind', sa.String(30), nullable=False),
        sa.Column('label', sa.String(100), nullable=False),
        sa.Column('config_json', sa.JSON(), nullable=False),
        sa.Column('encrypted_secret', sa.Text()),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('last_checked_at', sa.DateTime(timezone=True)),
        sa.Column('last_check_status', sa.String(30)),
        sa.Column('last_check_detail', sa.String(200)),
        sa.Column('created_by', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('SEARCH_TAVILY','SEARCH_BRAVE','ACCESSTRADE','FACEBOOK_PAGE')", name='ck_integration_kind'),
        sa.CheckConstraint("last_check_status IS NULL OR last_check_status IN ('OK','AUTH_FAILED','RATE_LIMITED','PROVIDER_ERROR','INVALID_RESPONSE','UNREACHABLE')",
                           name='ck_integration_check_status'),
        sa.CheckConstraint('archived = false OR encrypted_secret IS NULL', name='ck_integration_archived_no_secret'),
    )
    op.create_index('ix_integrations_kind', 'integrations', ['kind', 'archived'])
    op.create_index('uq_integrations_active_label', 'integrations', ['kind', 'label'], unique=True, postgresql_where=sa.text('archived = false'))


def downgrade() -> None:
    raise RuntimeError('Forward-only migration')
