"""Add controlled workflow records; forward only.

Revision ID: 20261103_0005
Revises: 20261102_0004
"""
from alembic import op
import sqlalchemy as sa

revision = '20261103_0005'
down_revision = '20261102_0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid()
    tz = sa.DateTime(timezone=True)
    now = sa.text('now()')
    op.create_table('workflows',
        sa.Column('id', uuid, primary_key=True), sa.Column('opportunity_id', uuid, sa.ForeignKey('opportunities.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False), sa.Column('description', sa.String(5000)), sa.Column('status', sa.String(30), nullable=False, server_default='DRAFT'),
        sa.Column('created_by', sa.String(100), nullable=False), sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', tz, nullable=False, server_default=now), sa.Column('updated_at', tz, nullable=False, server_default=now),
        sa.Column('started_at', tz), sa.Column('completed_at', tz), sa.Column('cancelled_at', tz),
        sa.CheckConstraint("status IN ('DRAFT','PENDING_APPROVAL','APPROVED','QUEUED','RUNNING','PAUSED','COMPLETED','FAILED','CANCELLED')", name='ck_workflow_status'),
        sa.CheckConstraint('version >= 1', name='ck_workflow_version'))
    op.create_index('ix_workflow_status_created', 'workflows', ['status', 'created_at'])
    op.create_index('ix_workflow_opportunity', 'workflows', ['opportunity_id'])
    op.create_table('workflow_tasks',
        sa.Column('id', uuid, primary_key=True), sa.Column('workflow_id', uuid, sa.ForeignKey('workflows.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False), sa.Column('description', sa.String(5000)), sa.Column('task_type', sa.String(100), nullable=False),
        sa.Column('assigned_role', sa.String(100), nullable=False), sa.Column('status', sa.String(30), nullable=False, server_default='PENDING'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'), sa.Column('max_retries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'), sa.Column('timeout_seconds', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('input_json', sa.JSON(), nullable=False), sa.Column('created_at', tz, nullable=False, server_default=now), sa.Column('started_at', tz), sa.Column('finished_at', tz),
        sa.UniqueConstraint('workflow_id', 'id', name='uq_workflow_task_parent_id'),
        sa.CheckConstraint("status IN ('PENDING','BLOCKED','READY','RUNNING','SUCCEEDED','FAILED','RETRY_WAIT','CANCELLED','SKIPPED')", name='ck_workflow_task_status'),
        sa.CheckConstraint('max_retries >= 0 AND max_retries <= 10 AND retry_count >= 0 AND retry_count <= max_retries', name='ck_workflow_task_retries'),
        sa.CheckConstraint('timeout_seconds BETWEEN 1 AND 300', name='ck_workflow_task_timeout'))
    op.create_index('ix_workflow_tasks_workflow_status', 'workflow_tasks', ['workflow_id', 'status'])
    op.create_table('task_dependencies', sa.Column('id', uuid, primary_key=True), sa.Column('workflow_id', uuid, nullable=False),
        sa.Column('task_id', uuid, nullable=False), sa.Column('depends_on_task_id', uuid, nullable=False),
        sa.ForeignKeyConstraint(['workflow_id', 'task_id'], ['workflow_tasks.workflow_id', 'workflow_tasks.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workflow_id', 'depends_on_task_id'], ['workflow_tasks.workflow_id', 'workflow_tasks.id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('task_id', 'depends_on_task_id', name='uq_task_dependency'), sa.CheckConstraint('task_id <> depends_on_task_id', name='ck_task_dependency_not_self'))
    op.create_index('ix_task_dependency_parent', 'task_dependencies', ['depends_on_task_id'])
    op.create_table('task_executions', sa.Column('id', uuid, primary_key=True), sa.Column('task_id', uuid, sa.ForeignKey('workflow_tasks.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False), sa.Column('status', sa.String(30), nullable=False), sa.Column('started_at', tz, nullable=False, server_default=now),
        sa.Column('completed_at', tz), sa.Column('lease_expires_at', tz), sa.Column('error_code', sa.String(100)), sa.Column('error_message', sa.String(1000)),
        sa.Column('output_reference', sa.String(500)), sa.Column('output_json', sa.JSON()), sa.Column('idempotency_key', sa.String(255), nullable=False),
        sa.UniqueConstraint('task_id', 'attempt_number', name='uq_task_execution_attempt'), sa.UniqueConstraint('idempotency_key', name='uq_task_execution_idempotency'),
        sa.CheckConstraint('attempt_number >= 1', name='ck_task_execution_attempt'), sa.CheckConstraint("status IN ('RUNNING','SUCCEEDED','FAILED','CANCELLED','TIMED_OUT','ABANDONED')", name='ck_task_execution_status'))
    op.create_index('ix_task_execution_task_started', 'task_executions', ['task_id', 'started_at'])
    op.create_index('ix_task_execution_lease', 'task_executions', ['status', 'lease_expires_at'])
    op.create_table('workflow_events', sa.Column('id', uuid, primary_key=True), sa.Column('workflow_id', uuid, sa.ForeignKey('workflows.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('task_id', uuid, sa.ForeignKey('workflow_tasks.id', ondelete='RESTRICT')), sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('previous_status', sa.String(30)), sa.Column('new_status', sa.String(30)), sa.Column('actor', sa.String(100), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False), sa.Column('created_at', tz, nullable=False, server_default=now),
        sa.ForeignKeyConstraint(['workflow_id', 'task_id'], ['workflow_tasks.workflow_id', 'workflow_tasks.id'], ondelete='RESTRICT'))
    op.create_index('ix_workflow_events_workflow_created', 'workflow_events', ['workflow_id', 'created_at'])


def downgrade() -> None:
    raise RuntimeError('Forward-only migration: workflow execution history must be preserved')
