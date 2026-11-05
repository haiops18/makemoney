"""Persist billing-sensitive AI invocation identity and unknown usage.

Revision ID: 20261105_0016
Revises: 20261105_0015
"""
from alembic import op
import sqlalchemy as sa

revision = '20261105_0016'
down_revision = '20261105_0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('ai_invocations',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('execution_id', sa.Uuid(), sa.ForeignKey('task_executions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('research_run_id', sa.Uuid(), sa.ForeignKey('ai_research_runs.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('provider_id', sa.Uuid(), sa.ForeignKey('ai_providers.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('profile_id', sa.Uuid(), sa.ForeignKey('ai_agent_profiles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('prompt_version_id', sa.Uuid(), sa.ForeignKey('ai_prompt_versions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('price_id', sa.Uuid(), sa.ForeignKey('ai_model_prices.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('reservation_id', sa.Uuid(), sa.ForeignKey('budget_reservations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('usage_record_id', sa.Uuid(), sa.ForeignKey('usage_records.id', ondelete='RESTRICT')),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('model_id', sa.String(200), nullable=False),
        sa.Column('agent_role', sa.String(100), nullable=False),
        sa.Column('request_snapshot_json', sa.JSON(), nullable=False),
        sa.Column('provider_request_id', sa.String(200)),
        sa.Column('input_tokens', sa.Integer()),
        sa.Column('output_tokens', sa.Integer()),
        sa.Column('estimated_cost', sa.Numeric(18, 6), nullable=False),
        sa.Column('calculated_cost', sa.Numeric(18, 6)),
        sa.Column('error_code', sa.String(100)),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('execution_id', name='uq_ai_invocation_execution'),
        sa.UniqueConstraint('reservation_id', name='uq_ai_invocation_reservation'),
        sa.UniqueConstraint('usage_record_id', name='uq_ai_invocation_usage'),
        sa.UniqueConstraint('provider_id', 'provider_request_id', name='uq_ai_invocation_provider_request'),
        sa.CheckConstraint("status IN ('PREPARED','DISPATCHED','SUCCEEDED','FAILED','USAGE_UNKNOWN')", name='ck_ai_invocation_status'),
        sa.CheckConstraint('input_tokens IS NULL OR input_tokens >= 0', name='ck_ai_invocation_input_tokens'),
        sa.CheckConstraint('output_tokens IS NULL OR output_tokens >= 0', name='ck_ai_invocation_output_tokens'),
        sa.CheckConstraint('estimated_cost >= 0 AND (calculated_cost IS NULL OR calculated_cost >= 0)', name='ck_ai_invocation_cost'))
    op.create_index('ix_ai_invocations_status_created', 'ai_invocations', ['status', 'created_at'])


def downgrade() -> None:
    raise RuntimeError('Forward-only migration: AI invocation and charge history must be preserved')
