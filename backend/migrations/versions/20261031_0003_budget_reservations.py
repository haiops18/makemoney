"""finance and budget reservations

Revision ID: 20261031_0003
Revises: 20261031_0002
Create Date: 2026-10-31
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0003"
down_revision = "20261031_0002"
branch_labels = None
depends_on = None


def money() -> sa.Numeric:
    return sa.Numeric(18, 6)


def upgrade() -> None:
    op.create_table(
        "budget_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("limit_amount", money(), nullable=False),
        sa.Column("reserve_amount", money(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("name", "period_start", name="uq_budget_account_name_period"),
        sa.CheckConstraint("currency = 'USD'", name="ck_budget_account_currency"),
        sa.CheckConstraint("limit_amount >= 0 AND reserve_amount >= 0 AND reserve_amount <= limit_amount", name="ck_budget_account_amounts"),
        sa.CheckConstraint("period_end > period_start", name="ck_budget_account_period"),
        sa.CheckConstraint("status IN ('ACTIVE', 'CLOSED')", name="ck_budget_account_status"),
    )
    op.create_table(
        "budget_reservations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("budget_account_id", sa.Uuid(), sa.ForeignKey("budget_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("reserved_amount", money(), nullable=False),
        sa.Column("actual_amount", money()),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("budget_account_id", "task_id", name="uq_budget_reservation_account_task"),
        sa.UniqueConstraint("budget_account_id", "idempotency_key", name="uq_budget_reservation_account_key"),
        sa.CheckConstraint("reserved_amount > 0", name="ck_budget_reservation_reserved"),
        sa.CheckConstraint("actual_amount IS NULL OR (actual_amount >= 0 AND actual_amount <= reserved_amount)", name="ck_budget_reservation_actual"),
        sa.CheckConstraint("status IN ('ACTIVE', 'SETTLED', 'RELEASED', 'EXPIRED')", name="ck_budget_reservation_status"),
    )
    op.create_index("ix_budget_reservations_account_status_expires", "budget_reservations", ["budget_account_id", "status", "expires_at"])
    op.create_table(
        "usage_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_run_id", sa.Uuid()),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", money(), nullable=False),
        sa.Column("actual_cost", money()),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("currency = 'USD'", name="ck_usage_record_currency"),
        sa.CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="ck_usage_record_tokens"),
        sa.CheckConstraint("estimated_cost >= 0 AND (actual_cost IS NULL OR actual_cost >= 0)", name="ck_usage_record_costs"),
    )
    op.create_index("ix_usage_records_recorded_at", "usage_records", ["recorded_at"])
    op.create_table(
        "cost_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid()),
        sa.Column("task_id", sa.Uuid()),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("amount", money(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("currency = 'USD'", name="ck_cost_record_currency"),
        sa.CheckConstraint("amount >= 0", name="ck_cost_record_amount"),
        sa.CheckConstraint("status IN ('ESTIMATED', 'CONFIRMED', 'PENDING_RECONCILIATION')", name="ck_cost_record_status"),
    )
    op.create_index("ix_cost_records_created_at", "cost_records", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_cost_records_created_at", table_name="cost_records")
    op.drop_table("cost_records")
    op.drop_index("ix_usage_records_recorded_at", table_name="usage_records")
    op.drop_table("usage_records")
    op.drop_index("ix_budget_reservations_account_status_expires", table_name="budget_reservations")
    op.drop_table("budget_reservations")
    op.drop_table("budget_accounts")
