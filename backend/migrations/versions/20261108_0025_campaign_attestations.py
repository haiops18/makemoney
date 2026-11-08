"""Step 7B: the Owner's standing campaign attestations (media rights, ads/e-commerce/tax).

Forward-only.

Revision ID: 20261108_0025
Revises: 20261108_0024
"""
from alembic import op
import sqlalchemy as sa

revision = '20261108_0025'
down_revision = '20261108_0024'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'campaign_attestations',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('campaign_id', sa.Uuid(), sa.ForeignKey('campaigns.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('check_name', sa.String(30), nullable=False),
        sa.Column('note', sa.String(1000), nullable=False),
        sa.Column('attested_by', sa.String(100), nullable=False),
        sa.Column('attested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("check_name IN ('MEDIA_RIGHTS','LEGAL_ADS_TAX')", name='ck_campaign_attestation_check'),
    )
    op.create_index('uq_campaign_attestation_active', 'campaign_attestations', ['campaign_id', 'check_name'], unique=True, postgresql_where=sa.text('revoked_at IS NULL'))


def downgrade() -> None:
    raise RuntimeError('Forward-only migration')
