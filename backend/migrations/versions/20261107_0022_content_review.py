"""Step 7A Level B review: content checks, Owner decisions and publish records.

Forward-only. Nothing here publishes; publish records are the Owner's own report.

Revision ID: 20261107_0022
Revises: 20261107_0021
"""
from alembic import op
import sqlalchemy as sa

revision = '20261107_0022'
down_revision = '20261107_0021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('content_items', sa.Column('decided_by', sa.String(100)))
    op.add_column('content_items', sa.Column('decided_at', sa.DateTime(timezone=True)))
    op.add_column('content_items', sa.Column('decision_note', sa.String(1000)))
    op.create_table(
        'content_checks',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('version_id', sa.Uuid(), sa.ForeignKey('content_versions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('check_name', sa.String(30), nullable=False),
        sa.Column('result', sa.String(20), nullable=False),
        sa.Column('method', sa.String(10), nullable=False),
        sa.Column('note', sa.String(1000), nullable=False),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('attested_by', sa.String(100)),
        sa.Column('attested_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("result IN ('PASS','FAIL','NEEDS_OWNER')", name='ck_content_check_result'),
        sa.CheckConstraint("method IN ('RULE','OWNER')", name='ck_content_check_method'),
        sa.CheckConstraint("(method = 'OWNER') = (attested_by IS NOT NULL)", name='ck_content_check_attested'),
        sa.UniqueConstraint('version_id', 'check_name', name='uq_content_check_version'),
    )
    op.create_table(
        'content_publish_records',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('content_id', sa.Uuid(), sa.ForeignKey('content_items.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('version_no', sa.Integer(), nullable=False),
        sa.Column('channel', sa.String(100), nullable=False),
        sa.Column('published_url', sa.String(2048), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('recorded_by', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('content_id', 'published_url', name='uq_content_publish_url'),
    )


def downgrade() -> None:
    raise RuntimeError('Forward-only migration: review history must be preserved')
