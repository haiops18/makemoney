"""policy and approval engine

Revision ID: 20261031_0002
Revises: 20261030_0001
Create Date: 2026-10-31
"""

import json
import uuid

from alembic import op
import sqlalchemy as sa

revision = "20261031_0002"
down_revision = "20261030_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("rules_json", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("name", "version", name="uq_policy_name_version"),
    )
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("policy_id", sa.Uuid(), sa.ForeignKey("policies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("action_hash", sa.String(64), nullable=False),
        sa.Column("action_payload_json", sa.JSON(), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("reason", sa.String(500)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'CONSUMED')", name="ck_approval_request_status"),
    )
    op.create_index("ix_approval_requests_status_expires_at", "approval_requests", ["status", "expires_at"])
    op.create_index("ix_approval_requests_action_hash", "approval_requests", ["action_hash"])
    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("approval_id", sa.Uuid(), sa.ForeignKey("approval_requests.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decided_by", sa.String(100), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("approval_id", name="uq_approval_decision_approval"),
        sa.CheckConstraint("decision IN ('APPROVE', 'REJECT')", name="ck_approval_decision_decision"),
    )
    op.create_table(
        "action_authorizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("approval_id", sa.Uuid(), sa.ForeignKey("approval_requests.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action_hash", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.UniqueConstraint("approval_id", name="uq_action_authorization_approval"),
        sa.CheckConstraint("scope IN ('ONCE')", name="ck_action_authorization_scope"),
        sa.CheckConstraint("status IN ('ACTIVE', 'CONSUMED', 'EXPIRED', 'REVOKED')", name="ck_action_authorization_status"),
        sa.CheckConstraint("consumed_at IS NULL OR status = 'CONSUMED'", name="ck_action_authorization_consumed"),
    )
    op.create_index("ix_action_authorizations_status_expires_at", "action_authorizations", ["status", "expires_at"])
    policy_id = uuid.uuid4()
    rules = json.dumps({"allowed_action_types": ["INTERNAL_WORKFLOW", "OPPORTUNITY_REVIEW"], "authorization_scope": "ONCE", "external_execution": False, "require_approval": True})
    op.execute(
        "INSERT INTO policies (id, name, version, description, rules_json, enabled) "
        f"VALUES ('{policy_id}', 'owner-controlled-internal', '1.0', "
        "'Allows only approved internal Sprint 2 actions with one-time authorization.', "
        f"'{rules}'::jsonb, true)"
    )


def downgrade() -> None:
    op.drop_index("ix_action_authorizations_status_expires_at", table_name="action_authorizations")
    op.drop_table("action_authorizations")
    op.drop_table("approval_decisions")
    op.drop_index("ix_approval_requests_action_hash", table_name="approval_requests")
    op.drop_index("ix_approval_requests_status_expires_at", table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_table("policies")
