"""Add disabled AI control and a separate approval-required AI policy.

Revision ID: 20261105_0014
Revises: 20261105_0013
"""
import uuid
from alembic import op
import sqlalchemy as sa

revision = '20261105_0014'
down_revision = '20261105_0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    control = op.create_table('ai_execution_controls',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('name', sa.String(20), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('name', name='uq_ai_execution_control_name'),
        sa.CheckConstraint("name = 'primary'", name='ck_ai_execution_control_singleton'),
        sa.CheckConstraint('version >= 1', name='ck_ai_execution_control_version'))
    op.bulk_insert(control, [{'id': uuid.uuid4(), 'name': 'primary', 'enabled': False, 'version': 1}])
    policies = sa.table('policies', sa.column('id', sa.Uuid()), sa.column('name', sa.String()),
                        sa.column('version', sa.String()), sa.column('description', sa.String()),
                        sa.column('rules_json', sa.JSON()), sa.column('enabled', sa.Boolean()))
    op.bulk_insert(policies, [{
        'id': uuid.uuid4(), 'name': 'ai-inference-controlled', 'version': '1.0',
        'description': 'Owner-approved AI inference only; external business execution remains disabled.',
        'rules_json': {'allowed_action_types': ['AI_CONTROL_ENABLE', 'AI_INFERENCE'], 'authorization_scope': 'ONCE',
                       'require_approval': True, 'external_execution': False, 'ai_inference_allowed': True},
        'enabled': True,
    }])


def downgrade() -> None:
    raise RuntimeError('Forward-only migration: AI control history must be preserved')
