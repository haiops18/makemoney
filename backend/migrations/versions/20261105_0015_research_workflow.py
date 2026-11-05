"""Allow an existing workflow to originate from a research draft.

Revision ID: 20261105_0015
Revises: 20261105_0014
"""
from alembic import op
import sqlalchemy as sa

revision = '20261105_0015'
down_revision = '20261105_0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('workflows', sa.Column('research_run_id', sa.Uuid(), nullable=True))
    op.create_foreign_key('fk_workflow_research_run', 'workflows', 'ai_research_runs', ['research_run_id'], ['id'], ondelete='RESTRICT')
    op.create_unique_constraint('uq_workflow_research_run', 'workflows', ['research_run_id'])
    op.alter_column('workflows', 'opportunity_id', existing_type=sa.Uuid(), nullable=True)
    op.create_check_constraint('ck_workflow_one_root', 'workflows',
        '(opportunity_id IS NOT NULL AND research_run_id IS NULL) OR (opportunity_id IS NULL AND research_run_id IS NOT NULL)')


def downgrade() -> None:
    raise RuntimeError('Forward-only migration: workflow roots and history must be preserved')
