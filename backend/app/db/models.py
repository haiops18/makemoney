import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, Numeric, String, UniqueConstraint, func
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


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'RESEARCHING', 'EVALUATED', 'DISQUALIFIED', 'ARCHIVED')", name="ck_opportunity_status"),
        CheckConstraint("risk_level IN ('UNKNOWN', 'LOW', 'MEDIUM', 'HIGH', 'SEVERE')", name="ck_opportunity_risk_level"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_opportunity_score"),
        CheckConstraint("confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 100)", name="ck_opportunity_confidence"),
        CheckConstraint("time_to_validate_days IS NULL OR time_to_validate_days >= 0", name="ck_opportunity_validation_days"),
        Index("ix_opportunities_status_score", "status", "score"),
        Index("ix_opportunities_business_model_created_at", "business_model", "created_at"),
        Index("ix_opportunities_updated_at", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(5000))
    category: Mapped[str | None] = mapped_column(String(100))
    target_market: Mapped[str | None] = mapped_column(String(200))
    target_customer: Mapped[str | None] = mapped_column(String(500))
    business_model: Mapped[str] = mapped_column(String(100), nullable=False)
    monetization_method: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    score: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[int | None] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    time_to_validate_days: Mapped[int | None] = mapped_column(Integer)
    data_origin: Mapped[str] = mapped_column(String(100), nullable=False, default="OWNER_INPUT")
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class OpportunityEvidence(Base):
    __tablename__ = "opportunity_evidence"
    __table_args__ = (
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 100)", name="ck_opportunity_evidence_confidence"),
        CheckConstraint("verification_status IN ('UNVERIFIED', 'VERIFIED', 'REJECTED')", name="ck_opportunity_evidence_verification"),
        Index("ix_opportunity_evidence_opportunity_captured", "opportunity_id", "captured_at"),
        UniqueConstraint("opportunity_id", "source_url", "evidence_type", name="uq_opportunity_evidence_source_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id", ondelete="RESTRICT"), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str] = mapped_column(String(5000), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confidence: Mapped[int | None] = mapped_column(Integer)
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, default="UNVERIFIED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OpportunityEstimate(Base):
    __tablename__ = "opportunity_estimates"
    __table_args__ = (
        CheckConstraint("scenario IN ('PESSIMISTIC', 'BASE', 'OPTIMISTIC')", name="ck_opportunity_estimate_scenario"),
        CheckConstraint("length(currency) = 3", name="ck_opportunity_estimate_currency"),
        CheckConstraint("setup_cost IS NULL OR setup_cost >= 0", name="ck_opportunity_estimate_setup_cost"),
        CheckConstraint("monthly_operating_cost IS NULL OR monthly_operating_cost >= 0", name="ck_opportunity_estimate_operating_cost"),
        CheckConstraint("expected_monthly_revenue IS NULL OR expected_monthly_revenue >= 0", name="ck_opportunity_estimate_revenue"),
        CheckConstraint("confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 100)", name="ck_opportunity_estimate_confidence"),
        Index("ix_opportunity_estimates_opportunity_scenario_evaluated", "opportunity_id", "scenario", "evaluated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id", ondelete="RESTRICT"), nullable=False)
    scenario: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    setup_cost: Mapped[Any | None] = mapped_column(Numeric(18, 6))
    monthly_operating_cost: Mapped[Any | None] = mapped_column(Numeric(18, 6))
    expected_monthly_revenue: Mapped[Any | None] = mapped_column(Numeric(18, 6))
    expected_monthly_profit: Mapped[Any | None] = mapped_column(Numeric(18, 6))
    expected_roi: Mapped[Any | None] = mapped_column(Numeric(18, 6))
    break_even_months: Mapped[Any | None] = mapped_column(Numeric(18, 6))
    confidence_score: Mapped[int | None] = mapped_column(Integer)
    assumptions_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OpportunityScoreDetail(Base):
    __tablename__ = "opportunity_score_details"
    __table_args__ = (
        CheckConstraint("total_score >= 0 AND total_score <= 100", name="ck_opportunity_score_detail_total"),
        Index("ix_opportunity_score_details_opportunity_created", "opportunity_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id", ondelete="RESTRICT"), nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(50), nullable=False)
    market_demand_score: Mapped[Any] = mapped_column(Numeric(6, 3), nullable=False)
    monetization_score: Mapped[Any] = mapped_column(Numeric(6, 3), nullable=False)
    automation_score: Mapped[Any] = mapped_column(Numeric(6, 3), nullable=False)
    cost_efficiency_score: Mapped[Any] = mapped_column(Numeric(6, 3), nullable=False)
    competitive_advantage_score: Mapped[Any] = mapped_column(Numeric(6, 3), nullable=False)
    scalability_score: Mapped[Any] = mapped_column(Numeric(6, 3), nullable=False)
    evidence_confidence_score: Mapped[Any] = mapped_column(Numeric(6, 3), nullable=False)
    total_score: Mapped[Any] = mapped_column(Numeric(6, 3), nullable=False)
    disqualified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    disqualification_reason: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OpportunityEvaluation(Base):
    __tablename__ = "opportunity_evaluations"
    __table_args__ = (Index("ix_opportunity_evaluations_opportunity_evaluated", "opportunity_id", "evaluated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id", ondelete="RESTRICT"), nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(50), nullable=False)
    input_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evaluated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Workflow(Base):
    __tablename__ = 'workflows'
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','PENDING_APPROVAL','APPROVED','QUEUED','RUNNING','PAUSED','COMPLETED','FAILED','CANCELLED')", name='ck_workflow_status'),
        CheckConstraint('version >= 1', name='ck_workflow_version'),
        Index('ix_workflow_status_created', 'status', 'created_at'),
        Index('ix_workflow_opportunity', 'opportunity_id'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('opportunities.id', ondelete='RESTRICT'), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(5000))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='DRAFT', server_default='DRAFT')
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowTask(Base):
    __tablename__ = 'workflow_tasks'
    __table_args__ = (
        UniqueConstraint('workflow_id', 'id', name='uq_workflow_task_parent_id'),
        CheckConstraint("status IN ('PENDING','BLOCKED','READY','RUNNING','SUCCEEDED','FAILED','RETRY_WAIT','CANCELLED','SKIPPED')", name='ck_workflow_task_status'),
        CheckConstraint('max_retries >= 0 AND max_retries <= 10 AND retry_count >= 0 AND retry_count <= max_retries', name='ck_workflow_task_retries'),
        CheckConstraint('timeout_seconds BETWEEN 1 AND 300', name='ck_workflow_task_timeout'),
        Index('ix_workflow_tasks_workflow_status', 'workflow_id', 'status'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('workflows.id', ondelete='RESTRICT'), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(5000))
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    assigned_role: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='PENDING', server_default='PENDING')
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30, server_default='30')
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskDependency(Base):
    __tablename__ = 'task_dependencies'
    __table_args__ = (
        ForeignKeyConstraint(['workflow_id', 'task_id'], ['workflow_tasks.workflow_id', 'workflow_tasks.id'], ondelete='RESTRICT'),
        ForeignKeyConstraint(['workflow_id', 'depends_on_task_id'], ['workflow_tasks.workflow_id', 'workflow_tasks.id'], ondelete='RESTRICT'),
        UniqueConstraint('task_id', 'depends_on_task_id', name='uq_task_dependency'),
        CheckConstraint('task_id <> depends_on_task_id', name='ck_task_dependency_not_self'),
        Index('ix_task_dependency_parent', 'depends_on_task_id'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    depends_on_task_id: Mapped[uuid.UUID] = mapped_column(nullable=False)


class TaskExecution(Base):
    __tablename__ = 'task_executions'
    __table_args__ = (
        UniqueConstraint('task_id', 'attempt_number', name='uq_task_execution_attempt'),
        UniqueConstraint('idempotency_key', name='uq_task_execution_idempotency'),
        CheckConstraint('attempt_number >= 1', name='ck_task_execution_attempt'),
        CheckConstraint("status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED','TIMED_OUT','ABANDONED')", name='ck_task_execution_status'),
        UniqueConstraint('authorization_id', name='uq_task_execution_authorization'),
        Index('ix_task_execution_task_started', 'task_id', 'started_at'),
        Index('ix_task_execution_lease', 'status', 'lease_expires_at'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('workflow_tasks.id', ondelete='RESTRICT'), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[uuid.UUID | None] = mapped_column()
    policy_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('policies.id', ondelete='RESTRICT'))
    authorization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('action_authorizations.id', ondelete='RESTRICT'))
    action_hash: Mapped[str | None] = mapped_column(String(64))
    input_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(String(1000))
    output_reference: Mapped[str | None] = mapped_column(String(500))
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)


class WorkflowEvent(Base):
    __tablename__ = 'workflow_events'
    __table_args__ = (
        ForeignKeyConstraint(['workflow_id', 'task_id'], ['workflow_tasks.workflow_id', 'workflow_tasks.id'], ondelete='RESTRICT'),
        Index('ix_workflow_events_workflow_created', 'workflow_id', 'created_at'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('workflows.id', ondelete='RESTRICT'), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('workflow_tasks.id', ondelete='RESTRICT'))
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(30))
    new_status: Mapped[str | None] = mapped_column(String(30))
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

