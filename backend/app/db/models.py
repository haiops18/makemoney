import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("actor", "key", name="uq_idempotency_actor_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_policy_name_version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    rules_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'CONSUMED')", name="ck_approval_request_status"),
        Index("ix_approval_requests_status_expires_at", "status", "expires_at"),
        Index("ix_approval_requests_action_hash", "action_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policies.id", ondelete="RESTRICT"), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    action_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    action_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    requested_by: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"
    __table_args__ = (
        UniqueConstraint("approval_id", name="uq_approval_decision_approval"),
        CheckConstraint("decision IN ('APPROVE', 'REJECT')", name="ck_approval_decision_decision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    approval_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approval_requests.id", ondelete="RESTRICT"), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(100), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ActionAuthorization(Base):
    __tablename__ = "action_authorizations"
    __table_args__ = (
        UniqueConstraint("approval_id", name="uq_action_authorization_approval"),
        CheckConstraint("scope IN ('ONCE')", name="ck_action_authorization_scope"),
        CheckConstraint("status IN ('ACTIVE', 'CONSUMED', 'EXPIRED', 'REVOKED')", name="ck_action_authorization_status"),
        CheckConstraint("consumed_at IS NULL OR status = 'CONSUMED'", name="ck_action_authorization_consumed"),
        Index("ix_action_authorizations_status_expires_at", "status", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    approval_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approval_requests.id", ondelete="RESTRICT"), nullable=False)
    action_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)


class BudgetAccount(Base):
    __tablename__ = "budget_accounts"
    __table_args__ = (
        UniqueConstraint("name", "period_start", name="uq_budget_account_name_period"),
        CheckConstraint("currency = 'USD'", name="ck_budget_account_currency"),
        CheckConstraint("limit_amount >= 0 AND reserve_amount >= 0 AND reserve_amount <= limit_amount", name="ck_budget_account_amounts"),
        CheckConstraint("period_end > period_start", name="ck_budget_account_period"),
        CheckConstraint("status IN ('ACTIVE', 'CLOSED')", name="ck_budget_account_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    limit_amount: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    reserve_amount: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class BudgetReservation(Base):
    __tablename__ = "budget_reservations"
    __table_args__ = (
        UniqueConstraint("budget_account_id", "task_id", name="uq_budget_reservation_account_task"),
        UniqueConstraint("budget_account_id", "idempotency_key", name="uq_budget_reservation_account_key"),
        CheckConstraint("reserved_amount > 0", name="ck_budget_reservation_reserved"),
        CheckConstraint("actual_amount IS NULL OR (actual_amount >= 0 AND actual_amount <= reserved_amount)", name="ck_budget_reservation_actual"),
        CheckConstraint("status IN ('ACTIVE', 'SETTLED', 'RELEASED', 'EXPIRED')", name="ck_budget_reservation_status"),
        Index("ix_budget_reservations_account_status_expires", "budget_account_id", "status", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    budget_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("budget_accounts.id", ondelete="RESTRICT"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    reserved_amount: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    actual_amount: Mapped[Any | None] = mapped_column(Numeric(18, 6))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class UsageRecord(Base):
    __tablename__ = "usage_records"
    __table_args__ = (
        CheckConstraint("currency = 'USD'", name="ck_usage_record_currency"),
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="ck_usage_record_tokens"),
        CheckConstraint("estimated_cost >= 0 AND (actual_cost IS NULL OR actual_cost >= 0)", name="ck_usage_record_costs"),
        Index("ix_usage_records_recorded_at", "recorded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column()
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    actual_cost: Mapped[Any | None] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CostRecord(Base):
    __tablename__ = "cost_records"
    __table_args__ = (
        CheckConstraint("currency = 'USD'", name="ck_cost_record_currency"),
        CheckConstraint("amount >= 0", name="ck_cost_record_amount"),
        CheckConstraint("status IN ('ESTIMATED', 'CONFIRMED', 'PENDING_RECONCILIATION')", name="ck_cost_record_status"),
        Index("ix_cost_records_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column()
    task_id: Mapped[uuid.UUID | None] = mapped_column()
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

