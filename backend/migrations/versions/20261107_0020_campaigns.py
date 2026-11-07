"""Step 7A campaigns: products, affiliate programs and terms, sources and links.

Level B data only; nothing here publishes, fetches or pays. Forward-only.

Revision ID: 20261107_0020
Revises: 20261106_0019
"""
from alembic import op
import sqlalchemy as sa

revision = '20261107_0020'
down_revision = '20261106_0019'
branch_labels = None
depends_on = None


def _owner_columns():
    return [sa.Column('created_by', sa.String(100), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def upgrade() -> None:
    op.create_table(
        'campaigns',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('opportunity_id', sa.Uuid(), sa.ForeignKey('opportunities.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('business_model', sa.String(100), nullable=False),
        sa.Column('niche', sa.String(200)),
        sa.Column('target_audience', sa.String(500)),
        sa.Column('goal', sa.String(2000)),
        sa.Column('language', sa.String(5), nullable=False),
        sa.Column('disclosure_text', sa.String(500)),
        sa.Column('max_cost_usd', sa.Numeric(18, 6), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        *_owner_columns(),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT','ACTIVE','PAUSED','ARCHIVED')", name='ck_campaign_status'),
        sa.CheckConstraint("language IN ('vi','en')", name='ck_campaign_language'),
        sa.CheckConstraint('max_cost_usd > 0 AND max_cost_usd <= 45', name='ck_campaign_cost'),
        sa.CheckConstraint('version >= 1', name='ck_campaign_version'),
    )
    op.create_index('ix_campaigns_status_created', 'campaigns', ['status', 'created_at'])
    op.create_index('ix_campaigns_opportunity', 'campaigns', ['opportunity_id'])

    op.create_table(
        'campaign_sources',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('campaign_id', sa.Uuid(), sa.ForeignKey('campaigns.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('source_name', sa.String(200), nullable=False),
        sa.Column('source_url', sa.String(2048)),
        sa.Column('excerpt', sa.Text(), nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('verification_status', sa.String(20), nullable=False),
        sa.Column('verified_by', sa.String(100)),
        sa.Column('verified_at', sa.DateTime(timezone=True)),
        sa.Column('verification_note', sa.String(1000)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("verification_status IN ('UNVERIFIED','VERIFIED','REJECTED')", name='ck_campaign_source_verification'),
        sa.CheckConstraint("(verification_status = 'UNVERIFIED') = (verified_at IS NULL)", name='ck_campaign_source_verifier'),
        sa.UniqueConstraint('campaign_id', 'id', name='uq_campaign_source_parent'),
    )
    op.create_index('ix_campaign_sources_campaign_created', 'campaign_sources', ['campaign_id', 'created_at', 'id'])

    op.create_table(
        'affiliate_programs',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('campaign_id', sa.Uuid(), sa.ForeignKey('campaigns.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('network', sa.String(30), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('join_url', sa.String(2048)),
        sa.Column('link_hosts', sa.JSON(), nullable=False),
        sa.Column('tracking_param_keys', sa.JSON(), nullable=False),
        *_owner_columns(),
        sa.CheckConstraint("network IN ('SHOPEE','TIKTOK_SHOP','ACCESSTRADE','ECOMOBI','LAZADA','OTHER')", name='ck_affiliate_program_network'),
        sa.UniqueConstraint('campaign_id', 'id', name='uq_affiliate_program_parent'),
        sa.UniqueConstraint('campaign_id', 'network', 'name', name='uq_affiliate_program_name'),
    )

    op.create_table(
        'affiliate_program_terms',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('campaign_id', sa.Uuid(), sa.ForeignKey('campaigns.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('program_id', sa.Uuid(), nullable=False),
        sa.Column('term', sa.String(40), nullable=False),
        sa.Column('value_text', sa.String(1000), nullable=False),
        sa.Column('value_numeric', sa.Numeric(18, 6)),
        sa.Column('unit', sa.String(10), nullable=False),
        sa.Column('source_id', sa.Uuid()),
        *_owner_columns(),
        sa.CheckConstraint("term IN ('JOIN_CONDITIONS','COMMISSION_MODEL','COMMISSION_RATE','COMMISSION_CAP','COOKIE_DAYS','ATTRIBUTION','PAYOUT','REFUND_CANCELLATION','TAX_WITHHOLDING')", name='ck_affiliate_term'),
        sa.CheckConstraint("unit IN ('NONE','PERCENT','VND','USD','DAYS')", name='ck_affiliate_term_unit'),
        sa.CheckConstraint("(value_numeric IS NULL) = (unit = 'NONE')", name='ck_affiliate_term_numeric_unit'),
        sa.ForeignKeyConstraint(['campaign_id', 'program_id'], ['affiliate_programs.campaign_id', 'affiliate_programs.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['campaign_id', 'source_id'], ['campaign_sources.campaign_id', 'campaign_sources.id'], ondelete='RESTRICT'),
    )
    op.create_index('ix_affiliate_terms_program', 'affiliate_program_terms', ['program_id', 'term', 'created_at'])

    op.create_table(
        'campaign_products',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('campaign_id', sa.Uuid(), sa.ForeignKey('campaigns.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('name', sa.String(300), nullable=False),
        sa.Column('merchant', sa.String(200)),
        sa.Column('product_url', sa.String(2048)),
        sa.Column('price_text', sa.String(100)),
        sa.Column('price_source_id', sa.Uuid()),
        sa.Column('notes', sa.String(2000)),
        *_owner_columns(),
        sa.UniqueConstraint('campaign_id', 'id', name='uq_campaign_product_parent'),
        sa.ForeignKeyConstraint(['campaign_id', 'price_source_id'], ['campaign_sources.campaign_id', 'campaign_sources.id'], ondelete='RESTRICT'),
        sa.CheckConstraint('price_text IS NULL OR price_source_id IS NOT NULL', name='ck_campaign_product_price_source'),
    )

    op.create_table(
        'affiliate_links',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('campaign_id', sa.Uuid(), sa.ForeignKey('campaigns.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('program_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid()),
        sa.Column('label', sa.String(200), nullable=False),
        sa.Column('original_url', sa.String(2048), nullable=False),
        sa.Column('tracking_params', sa.JSON(), nullable=False),
        sa.Column('final_url', sa.String(2048), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        *_owner_columns(),
        sa.Column('retired_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('ACTIVE','RETIRED')", name='ck_affiliate_link_status'),
        sa.CheckConstraint("(status = 'RETIRED') = (retired_at IS NOT NULL)", name='ck_affiliate_link_retired'),
        sa.ForeignKeyConstraint(['campaign_id', 'program_id'], ['affiliate_programs.campaign_id', 'affiliate_programs.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['campaign_id', 'product_id'], ['campaign_products.campaign_id', 'campaign_products.id'], ondelete='RESTRICT'),
    )
    op.create_index('uq_affiliate_link_active_url', 'affiliate_links', ['campaign_id', 'final_url'], unique=True, postgresql_where=sa.text("status = 'ACTIVE'"))


def downgrade() -> None:
    raise RuntimeError('Forward-only migration: campaign data cannot be dropped automatically')
