"""Persist execution authorization snapshots and fencing leases.

Revision ID: 20261103_0006
Revises: 20261103_0005
"""
from alembic import op
import sqlalchemy as sa

revision = '20261103_0006'
down_revision = '20261103_0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('workflow_tasks', sa.Column('next_retry_at', sa.DateTime(timezone=True)))
    op.add_column('task_executions', sa.Column('lease_token', sa.Uuid()))
    op.add_column('task_executions', sa.Column('policy_id', sa.Uuid()))
    op.add_column('task_executions', sa.Column('authorization_id', sa.Uuid()))
    op.add_column('task_executions', sa.Column('action_hash', sa.String(64)))
    op.add_column('task_executions', sa.Column('input_snapshot_json', sa.JSON()))
    op.create_foreign_key('fk_execution_policy', 'task_executions', 'policies', ['policy_id'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key('fk_execution_authorization', 'task_executions', 'action_authorizations', ['authorization_id'], ['id'], ondelete='RESTRICT')
    op.create_unique_constraint('uq_task_execution_authorization', 'task_executions', ['authorization_id'])
    op.drop_constraint('ck_task_execution_status', 'task_executions', type_='check')
    op.create_check_constraint('ck_task_execution_status', 'task_executions', "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED','TIMED_OUT','ABANDONED')")


def downgrade() -> None:
    raise RuntimeError('Forward-only migration: execution and authorization history must be preserved')
