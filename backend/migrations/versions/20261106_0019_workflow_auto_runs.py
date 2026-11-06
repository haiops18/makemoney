"""Workflow auto-run: one Owner approval queues every task of a workflow in order.

Adds workflow_auto_runs and task_executions.auto_run_id. Forward-only; existing
per-task approvals keep working unchanged.

Revision ID: 20261106_0019
Revises: 20261105_0018
"""
from alembic import op
import sqlalchemy as sa

revision = '20261106_0019'
down_revision = '20261105_0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'workflow_auto_runs',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('workflow_id', sa.Uuid(), sa.ForeignKey('workflows.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('workflow_version', sa.Integer(), nullable=False),
        sa.Column('ai_policy_id', sa.Uuid(), sa.ForeignKey('policies.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('internal_policy_id', sa.Uuid(), sa.ForeignKey('policies.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('approval_id', sa.Uuid(), sa.ForeignKey('approval_requests.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('authorization_id', sa.Uuid(), sa.ForeignKey('action_authorizations.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('plan_hash', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('stop_reason', sa.String(300)),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('ACTIVE','COMPLETED','STOPPED')", name='ck_workflow_auto_run_status'),
        sa.UniqueConstraint('approval_id', name='uq_workflow_auto_run_approval'),
        sa.UniqueConstraint('authorization_id', name='uq_workflow_auto_run_authorization'),
    )
    op.create_index('uq_workflow_auto_run_active', 'workflow_auto_runs', ['workflow_id'], unique=True, postgresql_where=sa.text("status = 'ACTIVE'"))
    op.add_column('task_executions', sa.Column('auto_run_id', sa.Uuid(), sa.ForeignKey('workflow_auto_runs.id', ondelete='RESTRICT')))
    op.create_check_constraint('ck_task_execution_single_grant', 'task_executions', 'authorization_id IS NULL OR auto_run_id IS NULL')


def downgrade() -> None:
    raise RuntimeError('Forward-only migration')
