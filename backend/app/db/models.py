import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, func, text
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


class AIProvider(Base):
    __tablename__ = 'ai_providers'
    __table_args__ = (
        CheckConstraint("kind IN ('OPENAI','GEMINI','ANTHROPIC','OPENAI_COMPATIBLE')", name='ck_ai_provider_kind'),
        CheckConstraint('NOT (archived AND is_default)', name='ck_ai_provider_default_active'),
        Index('ix_ai_providers_created_at', 'created_at', 'id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(2048))
    default_model: Mapped[str] = mapped_column(String(200), nullable=False)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text())
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_status: Mapped[str | None] = mapped_column(String(30))
    last_check_model_listed: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


Index('uq_ai_providers_single_default', AIProvider.is_default, unique=True,
      postgresql_where=AIProvider.is_default.is_(True), sqlite_where=AIProvider.is_default.is_(True))


class AIModelPrice(Base):
    __tablename__ = 'ai_model_prices'
    __table_args__ = (
        UniqueConstraint('provider_id', 'model_id', 'version', name='uq_ai_model_price_version'),
        CheckConstraint("currency = 'USD'", name='ck_ai_model_price_currency'),
        CheckConstraint('input_per_million >= 0 AND output_per_million >= 0', name='ck_ai_model_price_nonnegative'),
        CheckConstraint('expires_at IS NULL OR expires_at > effective_at', name='ck_ai_model_price_period'),
        Index('ix_ai_model_prices_provider_model_effective', 'provider_id', 'model_id', 'effective_at'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('ai_providers.id', ondelete='RESTRICT'), nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default='USD')
    input_per_million: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    output_per_million: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_note: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIPromptVersion(Base):
    __tablename__ = 'ai_prompt_versions'
    __table_args__ = (UniqueConstraint('name', 'version', name='uq_ai_prompt_name_version'),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    system_text: Mapped[str] = mapped_column(Text, nullable=False)
    developer_text: Mapped[str] = mapped_column(Text, nullable=False)
    input_schema_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    output_schema_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    constraints_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIExecutionControl(Base):
    __tablename__ = 'ai_execution_controls'
    __table_args__ = (
        UniqueConstraint('name', name='uq_ai_execution_control_name'),
        CheckConstraint("name = 'primary'", name='ck_ai_execution_control_singleton'),
        CheckConstraint('version >= 1', name='ck_ai_execution_control_version'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(20), nullable=False, default='primary')
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AIInvocation(Base):
    __tablename__ = 'ai_invocations'
    __table_args__ = (
        UniqueConstraint('execution_id', name='uq_ai_invocation_execution'),
        UniqueConstraint('reservation_id', name='uq_ai_invocation_reservation'),
        UniqueConstraint('usage_record_id', name='uq_ai_invocation_usage'),
        UniqueConstraint('provider_id', 'provider_request_id', name='uq_ai_invocation_provider_request'),
        CheckConstraint("status IN ('PREPARED','DISPATCHED','SUCCEEDED','FAILED','USAGE_UNKNOWN')", name='ck_ai_invocation_status'),
        CheckConstraint('input_tokens IS NULL OR input_tokens >= 0', name='ck_ai_invocation_input_tokens'),
        CheckConstraint('output_tokens IS NULL OR output_tokens >= 0', name='ck_ai_invocation_output_tokens'),
        CheckConstraint('estimated_cost >= 0 AND (calculated_cost IS NULL OR calculated_cost >= 0)', name='ck_ai_invocation_cost'),
        Index('ix_ai_invocations_status_created', 'status', 'created_at'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('task_executions.id', ondelete='RESTRICT'), nullable=False)
    research_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('ai_research_runs.id', ondelete='RESTRICT'), nullable=False)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('ai_providers.id', ondelete='RESTRICT'), nullable=False)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('ai_agent_profiles.id', ondelete='RESTRICT'), nullable=False)
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('ai_prompt_versions.id', ondelete='RESTRICT'), nullable=False)
    price_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('ai_model_prices.id', ondelete='RESTRICT'), nullable=False)
    reservation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('budget_reservations.id', ondelete='RESTRICT'), nullable=False)
    usage_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('usage_records.id', ondelete='RESTRICT'))
    status: Mapped[str] = mapped_column(String(30), default='PREPARED', nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    agent_role: Mapped[str] = mapped_column(String(100), nullable=False)
    request_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    calculated_cost: Mapped[Any | None] = mapped_column(Numeric(18, 6))
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIAgentProfile(Base):
    __tablename__ = 'ai_agent_profiles'
    __table_args__ = (
        UniqueConstraint('agent_id', name='uq_ai_agent_profile_agent'),
        CheckConstraint('max_output_tokens BETWEEN 1 AND 100000', name='ck_ai_profile_tokens'),
        CheckConstraint('timeout_seconds BETWEEN 1 AND 300', name='ck_ai_profile_timeout'),
        CheckConstraint('max_cost_usd > 0 AND max_cost_usd <= 45', name='ck_ai_profile_cost'),
        CheckConstraint('temperature IS NULL OR (temperature >= 0 AND temperature <= 2)', name='ck_ai_profile_temperature'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('agents.id', ondelete='RESTRICT'), nullable=False)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('ai_providers.id', ondelete='RESTRICT'), nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    temperature: Mapped[Any | None] = mapped_column(Numeric(3, 2))
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_cost_usd: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AIResearchRun(Base):
    __tablename__ = 'ai_research_runs'
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT')", name='ck_ai_research_run_status'),
        CheckConstraint('max_cost_usd > 0 AND max_cost_usd <= 45', name='ck_ai_research_run_cost'),
        CheckConstraint("kind IN ('RESEARCH','CONTENT')", name='ck_ai_research_run_kind'),
        CheckConstraint("(kind = 'CONTENT') = (campaign_id IS NOT NULL) AND (kind = 'CONTENT') = (content_spec_json IS NOT NULL)", name='ck_ai_research_run_content'),
        Index('ix_ai_research_runs_created_at', 'created_at', 'id'),
        Index('ix_ai_research_runs_campaign', 'campaign_id'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(150))
    target_market: Mapped[str | None] = mapped_column(String(200))
    target_customers: Mapped[str | None] = mapped_column(String(500))
    max_cost_usd: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='DRAFT', nullable=False)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('opportunities.id', ondelete='RESTRICT'), unique=True)
    # Step 7A: a CONTENT run is one content batch of a campaign, with a frozen input snapshot.
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default='RESEARCH', server_default='RESEARCH')
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('campaigns.id', ondelete='RESTRICT'))
    content_spec_json: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AIResearchSource(Base):
    __tablename__ = 'ai_research_sources'
    __table_args__ = (
        CheckConstraint("verification_status IN ('UNVERIFIED','VERIFIED','REJECTED')", name='ck_ai_research_source_verification'),
        CheckConstraint("(verification_status = 'UNVERIFIED') = (verified_at IS NULL)", name='ck_ai_research_source_verifier'),
        Index('ix_ai_research_sources_run_created', 'research_run_id', 'created_at', 'id'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    research_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('ai_research_runs.id', ondelete='RESTRICT'), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(20), default='UNVERIFIED', nullable=False)
    verified_by: Mapped[str | None] = mapped_column(String(100))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_note: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


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
        CheckConstraint("actual_amount IS NULL OR (actual_amount >= 0 AND (status = 'SETTLED' OR actual_amount <= reserved_amount))", name="ck_budget_reservation_actual"),
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
        CheckConstraint('(opportunity_id IS NOT NULL AND research_run_id IS NULL) OR (opportunity_id IS NULL AND research_run_id IS NOT NULL)', name='ck_workflow_one_root'),
        UniqueConstraint('research_run_id', name='uq_workflow_research_run'),
        Index('ix_workflow_status_created', 'status', 'created_at'),
        Index('ix_workflow_opportunity', 'opportunity_id'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('opportunities.id', ondelete='RESTRICT'))
    research_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('ai_research_runs.id', ondelete='RESTRICT'))
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
        CheckConstraint('authorization_id IS NULL OR auto_run_id IS NULL', name='ck_task_execution_single_grant'),
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
    # Set instead of authorization_id when an Owner-approved workflow auto-run queued this attempt.
    auto_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('workflow_auto_runs.id', ondelete='RESTRICT'))


class WorkflowAutoRun(Base):
    """One Owner approval that lets the worker queue every task of a workflow in order.

    The approval is bound to a server-derived plan hash (tasks, models, prices, prompts,
    sources, policies, cost ceiling). Every queue and dispatch recomputes the plan and
    stops the run when anything changed; per-call budget reservations still apply.
    """
    __tablename__ = 'workflow_auto_runs'
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','COMPLETED','STOPPED')", name='ck_workflow_auto_run_status'),
        UniqueConstraint('approval_id', name='uq_workflow_auto_run_approval'),
        UniqueConstraint('authorization_id', name='uq_workflow_auto_run_authorization'),
        Index('uq_workflow_auto_run_active', 'workflow_id', unique=True,
              postgresql_where=text("status = 'ACTIVE'"), sqlite_where=text("status = 'ACTIVE'")),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('workflows.id', ondelete='RESTRICT'), nullable=False)
    workflow_version: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('policies.id', ondelete='RESTRICT'), nullable=False)
    internal_policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('policies.id', ondelete='RESTRICT'), nullable=False)
    approval_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('approval_requests.id', ondelete='RESTRICT'), nullable=False)
    authorization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('action_authorizations.id', ondelete='RESTRICT'), nullable=False)
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='ACTIVE')
    stop_reason: Mapped[str | None] = mapped_column(String(300))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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



# Step 7A — campaigns. Level B only: nothing here publishes, fetches or pays.
class Campaign(Base):
    __tablename__ = 'campaigns'
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','ACTIVE','PAUSED','ARCHIVED')", name='ck_campaign_status'),
        CheckConstraint("language IN ('vi','en')", name='ck_campaign_language'),
        CheckConstraint('max_cost_usd > 0 AND max_cost_usd <= 45', name='ck_campaign_cost'),
        CheckConstraint('version >= 1', name='ck_campaign_version'),
        Index('ix_campaigns_status_created', 'status', 'created_at'),
        Index('ix_campaigns_opportunity', 'opportunity_id'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('opportunities.id', ondelete='RESTRICT'), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    business_model: Mapped[str] = mapped_column(String(100), nullable=False)
    niche: Mapped[str | None] = mapped_column(String(200))
    target_audience: Mapped[str | None] = mapped_column(String(500))
    goal: Mapped[str | None] = mapped_column(String(2000))
    language: Mapped[str] = mapped_column(String(5), nullable=False, default='vi')
    disclosure_text: Mapped[str | None] = mapped_column(String(500))
    max_cost_usd: Mapped[Any] = mapped_column(Numeric(18, 6), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='DRAFT')
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CampaignSource(Base):
    __tablename__ = 'campaign_sources'
    __table_args__ = (
        CheckConstraint("verification_status IN ('UNVERIFIED','VERIFIED','REJECTED')", name='ck_campaign_source_verification'),
        CheckConstraint("(verification_status = 'UNVERIFIED') = (verified_at IS NULL)", name='ck_campaign_source_verifier'),
        UniqueConstraint('campaign_id', 'id', name='uq_campaign_source_parent'),
        Index('ix_campaign_sources_campaign_created', 'campaign_id', 'created_at', 'id'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('campaigns.id', ondelete='RESTRICT'), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, default='UNVERIFIED')
    verified_by: Mapped[str | None] = mapped_column(String(100))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_note: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AffiliateProgram(Base):
    __tablename__ = 'affiliate_programs'
    __table_args__ = (
        CheckConstraint("network IN ('SHOPEE','TIKTOK_SHOP','ACCESSTRADE','ECOMOBI','LAZADA','OTHER')", name='ck_affiliate_program_network'),
        UniqueConstraint('campaign_id', 'id', name='uq_affiliate_program_parent'),
        UniqueConstraint('campaign_id', 'network', 'name', name='uq_affiliate_program_name'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('campaigns.id', ondelete='RESTRICT'), nullable=False)
    network: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    join_url: Mapped[str | None] = mapped_column(String(2048))
    # Owner-entered rules: links must use these hosts and may only add these query keys.
    link_hosts: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    tracking_param_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AffiliateProgramTerm(Base):
    __tablename__ = 'affiliate_program_terms'
    __table_args__ = (
        CheckConstraint("term IN ('JOIN_CONDITIONS','COMMISSION_MODEL','COMMISSION_RATE','COMMISSION_CAP','COOKIE_DAYS','ATTRIBUTION','PAYOUT','REFUND_CANCELLATION','TAX_WITHHOLDING')", name='ck_affiliate_term'),
        CheckConstraint("unit IN ('NONE','PERCENT','VND','USD','DAYS')", name='ck_affiliate_term_unit'),
        CheckConstraint("(value_numeric IS NULL) = (unit = 'NONE')", name='ck_affiliate_term_numeric_unit'),
        ForeignKeyConstraint(['campaign_id', 'program_id'], ['affiliate_programs.campaign_id', 'affiliate_programs.id'], ondelete='RESTRICT'),
        ForeignKeyConstraint(['campaign_id', 'source_id'], ['campaign_sources.campaign_id', 'campaign_sources.id'], ondelete='RESTRICT'),
        Index('ix_affiliate_terms_program', 'program_id', 'term', 'created_at'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('campaigns.id', ondelete='RESTRICT'), nullable=False)
    program_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    term: Mapped[str] = mapped_column(String(40), nullable=False)
    value_text: Mapped[str] = mapped_column(String(1000), nullable=False)
    value_numeric: Mapped[Any | None] = mapped_column(Numeric(18, 6))
    unit: Mapped[str] = mapped_column(String(10), nullable=False, default='NONE')
    source_id: Mapped[uuid.UUID | None] = mapped_column()
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CampaignProduct(Base):
    __tablename__ = 'campaign_products'
    __table_args__ = (
        UniqueConstraint('campaign_id', 'id', name='uq_campaign_product_parent'),
        ForeignKeyConstraint(['campaign_id', 'price_source_id'], ['campaign_sources.campaign_id', 'campaign_sources.id'], ondelete='RESTRICT'),
        CheckConstraint('price_text IS NULL OR price_source_id IS NOT NULL', name='ck_campaign_product_price_source'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('campaigns.id', ondelete='RESTRICT'), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(200))
    product_url: Mapped[str | None] = mapped_column(String(2048))
    price_text: Mapped[str | None] = mapped_column(String(100))
    price_source_id: Mapped[uuid.UUID | None] = mapped_column()
    notes: Mapped[str | None] = mapped_column(String(2000))
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AffiliateLink(Base):
    __tablename__ = 'affiliate_links'
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','RETIRED')", name='ck_affiliate_link_status'),
        CheckConstraint("(status = 'RETIRED') = (retired_at IS NOT NULL)", name='ck_affiliate_link_retired'),
        ForeignKeyConstraint(['campaign_id', 'program_id'], ['affiliate_programs.campaign_id', 'affiliate_programs.id'], ondelete='RESTRICT'),
        ForeignKeyConstraint(['campaign_id', 'product_id'], ['campaign_products.campaign_id', 'campaign_products.id'], ondelete='RESTRICT'),
        Index('uq_affiliate_link_active_url', 'campaign_id', 'final_url', unique=True,
              postgresql_where=text("status = 'ACTIVE'"), sqlite_where=text("status = 'ACTIVE'")),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('campaigns.id', ondelete='RESTRICT'), nullable=False)
    program_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column()
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    original_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    tracking_params: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    final_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='ACTIVE')
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


CONTENT_STATUSES = ('DRAFT', 'CHECK_FAILED', 'IN_REVIEW', 'APPROVED', 'REJECTED', 'READY_TO_PUBLISH', 'PUBLISHED')


class ContentItem(Base):
    __tablename__ = 'content_items'
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','CHECK_FAILED','IN_REVIEW','APPROVED','REJECTED','READY_TO_PUBLISH','PUBLISHED')", name='ck_content_item_status'),
        CheckConstraint("content_type IN ('REVIEW_ARTICLE','COMPARISON','VIDEO_SCRIPT','SHORT_CAPTION','SOCIAL_POST','CTA_LANDING')", name='ck_content_item_type'),
        CheckConstraint("language IN ('vi','en')", name='ck_content_item_language'),
        CheckConstraint('item_index >= 0 AND current_version_no >= 1', name='ck_content_item_numbers'),
        UniqueConstraint('source_invocation_id', 'item_index', name='uq_content_item_invocation_index'),
        UniqueConstraint('campaign_id', 'id', name='uq_content_item_parent'),
        Index('ix_content_items_campaign_status', 'campaign_id', 'status', 'created_at'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('campaigns.id', ondelete='RESTRICT'), nullable=False)
    batch_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('ai_research_runs.id', ondelete='RESTRICT'), nullable=False)
    source_invocation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('ai_invocations.id', ondelete='RESTRICT'), nullable=False)
    item_index: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('campaign_products.id', ondelete='RESTRICT'))
    affiliate_link_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('affiliate_links.id', ondelete='RESTRICT'), nullable=False)
    content_type: Mapped[str] = mapped_column(String(30), nullable=False)
    language: Mapped[str] = mapped_column(String(5), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='DRAFT')
    current_version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ContentVersion(Base):
    """Immutable text of one content item version (AI draft or Owner edit)."""
    __tablename__ = 'content_versions'
    __table_args__ = (
        CheckConstraint("author_kind IN ('AI','OWNER')", name='ck_content_version_author'),
        CheckConstraint("(author_kind = 'AI') = (invocation_id IS NOT NULL)", name='ck_content_version_invocation'),
        CheckConstraint('version_no >= 1 AND (base_version_no IS NULL OR base_version_no < version_no)', name='ck_content_version_numbers'),
        UniqueConstraint('content_id', 'version_no', name='uq_content_version_number'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    content_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('content_items.id', ondelete='RESTRICT'), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    base_version_no: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    cta: Mapped[str] = mapped_column(String(300), nullable=False)
    claims: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    author_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    invocation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('ai_invocations.id', ondelete='RESTRICT'))
    author: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
