"""Record actual settled costs even when providers bill above estimates.

Revision ID: 20261105_0013
Revises: 20261104_0012
"""
from alembic import op

revision = '20261105_0013'
down_revision = '20261104_0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint('ck_budget_reservation_actual', 'budget_reservations', type_='check')
    op.create_check_constraint('ck_budget_reservation_actual', 'budget_reservations',
        "actual_amount IS NULL OR (actual_amount >= 0 AND (status = 'SETTLED' OR actual_amount <= reserved_amount))")


def downgrade() -> None:
    raise RuntimeError('Forward-only migration: reconciled cost history must be preserved')
