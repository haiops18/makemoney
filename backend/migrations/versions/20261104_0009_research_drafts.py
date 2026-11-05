"""Persist Owner-entered research drafts and unverified source excerpts.

Revision ID: 20261104_0009
Revises: 20261104_0008
"""
from alembic import op
import sqlalchemy as sa

revision = '20261104_0009'
down_revision = '20261104_0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('ai_research_runs',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('objective', sa.Text(), nullable=False),
        sa.Column('category', sa.String(150)),
        sa.Column('target_market', sa.String(200)),
        sa.Column('target_customers', sa.String(500)),
        sa.Column('max_cost_usd', sa.Numeric(18, 6), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='DRAFT'),
        sa.Column('created_by', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT')", name='ck_ai_research_run_status'),
        sa.CheckConstraint('max_cost_usd > 0 AND max_cost_usd <= 45', name='ck_ai_research_run_cost'))
    op.create_index('ix_ai_research_runs_created_at', 'ai_research_runs', ['created_at', 'id'])
    op.create_table('ai_research_sources',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('research_run_id', sa.Uuid(), sa.ForeignKey('ai_research_runs.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('source_name', sa.String(200), nullable=False),
        sa.Column('source_url', sa.String(2048)),
        sa.Column('excerpt', sa.Text(), nullable=False),
        sa.Column('verification_status', sa.String(20), nullable=False, server_default='UNVERIFIED'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("verification_status IN ('UNVERIFIED')", name='ck_ai_research_source_verification'))
    op.create_index('ix_ai_research_sources_run_created', 'ai_research_sources', ['research_run_id', 'created_at', 'id'])


def downgrade() -> None:
    raise RuntimeError('Forward-only migration: research source history must be preserved')
