"""opportunity discovery and scoring

Revision ID: 20261102_0004
Revises: 20261031_0003
Create Date: 2026-11-02
"""

from alembic import op
import sqlalchemy as sa

revision = "20261102_0004"
down_revision = "20261031_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid()
    money = sa.Numeric(18, 6)
    op.create_table("opportunities",
        sa.Column("id", uuid, primary_key=True), sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(5000)), sa.Column("category", sa.String(100)), sa.Column("target_market", sa.String(200)),
        sa.Column("target_customer", sa.String(500)), sa.Column("business_model", sa.String(100), nullable=False),
        sa.Column("monetization_method", sa.String(200)), sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("score", sa.Integer()), sa.Column("confidence_score", sa.Integer()), sa.Column("risk_level", sa.String(20), nullable=False, server_default="UNKNOWN"),
        sa.Column("time_to_validate_days", sa.Integer()), sa.Column("data_origin", sa.String(100), nullable=False, server_default="OWNER_INPUT"),
        sa.Column("created_by", sa.String(100), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('DRAFT', 'RESEARCHING', 'EVALUATED', 'DISQUALIFIED', 'ARCHIVED')", name="ck_opportunity_status"),
        sa.CheckConstraint("risk_level IN ('UNKNOWN', 'LOW', 'MEDIUM', 'HIGH', 'SEVERE')", name="ck_opportunity_risk_level"),
        sa.CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_opportunity_score"),
        sa.CheckConstraint("confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 100)", name="ck_opportunity_confidence"),
        sa.CheckConstraint("time_to_validate_days IS NULL OR time_to_validate_days >= 0", name="ck_opportunity_validation_days"))
    op.create_index("ix_opportunities_status_score", "opportunities", ["status", "score"])
    op.create_index("ix_opportunities_business_model_created_at", "opportunities", ["business_model", "created_at"])
    op.create_index("ix_opportunities_updated_at", "opportunities", ["updated_at"])
    op.create_table("opportunity_evidence",
        sa.Column("id", uuid, primary_key=True), sa.Column("opportunity_id", uuid, sa.ForeignKey("opportunities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_url", sa.String(2048)), sa.Column("source_name", sa.String(200), nullable=False), sa.Column("source_type", sa.String(100), nullable=False),
        sa.Column("evidence_type", sa.String(100), nullable=False), sa.Column("summary", sa.String(5000), nullable=False), sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Integer()), sa.Column("verification_status", sa.String(20), nullable=False, server_default="UNVERIFIED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 100)", name="ck_opportunity_evidence_confidence"),
        sa.CheckConstraint("verification_status IN ('UNVERIFIED', 'VERIFIED', 'REJECTED')", name="ck_opportunity_evidence_verification"),
        sa.UniqueConstraint("opportunity_id", "source_url", "evidence_type", name="uq_opportunity_evidence_source_type"))
    op.create_index("ix_opportunity_evidence_opportunity_captured", "opportunity_evidence", ["opportunity_id", "captured_at"])
    op.create_table("opportunity_estimates",
        sa.Column("id", uuid, primary_key=True), sa.Column("opportunity_id", uuid, sa.ForeignKey("opportunities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("scenario", sa.String(20), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("setup_cost", money), sa.Column("monthly_operating_cost", money),
        sa.Column("expected_monthly_revenue", money), sa.Column("expected_monthly_profit", money), sa.Column("expected_roi", money), sa.Column("break_even_months", money),
        sa.Column("confidence_score", sa.Integer()), sa.Column("assumptions_json", sa.JSON(), nullable=False), sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("scenario IN ('PESSIMISTIC', 'BASE', 'OPTIMISTIC')", name="ck_opportunity_estimate_scenario"), sa.CheckConstraint("char_length(currency) = 3", name="ck_opportunity_estimate_currency"),
        sa.CheckConstraint("setup_cost IS NULL OR setup_cost >= 0", name="ck_opportunity_estimate_setup_cost"), sa.CheckConstraint("monthly_operating_cost IS NULL OR monthly_operating_cost >= 0", name="ck_opportunity_estimate_operating_cost"),
        sa.CheckConstraint("expected_monthly_revenue IS NULL OR expected_monthly_revenue >= 0", name="ck_opportunity_estimate_revenue"), sa.CheckConstraint("confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 100)", name="ck_opportunity_estimate_confidence"))
    op.create_index("ix_opportunity_estimates_opportunity_scenario_evaluated", "opportunity_estimates", ["opportunity_id", "scenario", "evaluated_at"])
    op.create_table("opportunity_score_details",
        sa.Column("id", uuid, primary_key=True), sa.Column("opportunity_id", uuid, sa.ForeignKey("opportunities.id", ondelete="RESTRICT"), nullable=False), sa.Column("scoring_version", sa.String(50), nullable=False),
        sa.Column("market_demand_score", sa.Numeric(6, 3), nullable=False), sa.Column("monetization_score", sa.Numeric(6, 3), nullable=False), sa.Column("automation_score", sa.Numeric(6, 3), nullable=False), sa.Column("cost_efficiency_score", sa.Numeric(6, 3), nullable=False),
        sa.Column("competitive_advantage_score", sa.Numeric(6, 3), nullable=False), sa.Column("scalability_score", sa.Numeric(6, 3), nullable=False), sa.Column("evidence_confidence_score", sa.Numeric(6, 3), nullable=False), sa.Column("total_score", sa.Numeric(6, 3), nullable=False),
        sa.Column("disqualified", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("disqualification_reason", sa.String(1000)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("total_score >= 0 AND total_score <= 100", name="ck_opportunity_score_detail_total"))
    op.create_index("ix_opportunity_score_details_opportunity_created", "opportunity_score_details", ["opportunity_id", "created_at"])
    op.create_table("opportunity_evaluations",
        sa.Column("id", uuid, primary_key=True), sa.Column("opportunity_id", uuid, sa.ForeignKey("opportunities.id", ondelete="RESTRICT"), nullable=False), sa.Column("scoring_version", sa.String(50), nullable=False),
        sa.Column("input_snapshot_json", sa.JSON(), nullable=False), sa.Column("result_snapshot_json", sa.JSON(), nullable=False), sa.Column("evaluated_by", sa.String(100), nullable=False), sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_opportunity_evaluations_opportunity_evaluated", "opportunity_evaluations", ["opportunity_id", "evaluated_at"])


def downgrade() -> None:
    raise RuntimeError("Forward-only migration: opportunity and evaluation history must be preserved")
