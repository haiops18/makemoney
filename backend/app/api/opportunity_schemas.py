from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Money = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6)]
ScoreInput = Annotated[int, Field(ge=0, le=100)]

BUSINESS_MODELS = {"MICRO_SAAS", "DIGITAL_PRODUCTS", "AFFILIATE_MARKETING", "CONTENT_MARKETING", "AI_SERVICES"}
STATUSES = {"DRAFT", "RESEARCHING", "EVALUATED", "DISQUALIFIED", "ARCHIVED"}
RISK_LEVELS = {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "SEVERE"}


class OpportunityCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = Field(default=None, max_length=100)
    target_market: str | None = Field(default=None, max_length=200)
    target_customer: str | None = Field(default=None, max_length=500)
    business_model: str = Field(min_length=1, max_length=100)
    monetization_method: str | None = Field(default=None, max_length=200)
    time_to_validate_days: int | None = Field(default=None, ge=0)
    data_origin: str = Field(default="OWNER_INPUT", min_length=1, max_length=100)

    @field_validator("business_model", "data_origin", mode="before")
    @classmethod
    def normalized_identifier(cls, value: str) -> str:
        return value.strip().upper()


class OpportunityUpdate(BaseModel):
    @model_validator(mode="after")
    def reject_null_required_fields(self):
        for name in {"title", "business_model", "data_origin", "status"} & self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = Field(default=None, max_length=100)
    target_market: str | None = Field(default=None, max_length=200)
    target_customer: str | None = Field(default=None, max_length=500)
    business_model: str | None = Field(default=None, min_length=1, max_length=100)
    monetization_method: str | None = Field(default=None, max_length=200)
    time_to_validate_days: int | None = Field(default=None, ge=0)
    data_origin: str | None = Field(default=None, min_length=1, max_length=100)
    status: Literal["DRAFT", "RESEARCHING", "ARCHIVED"] | None = None

    @field_validator("business_model", "data_origin", mode="before")
    @classmethod
    def normalized_identifier(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class OpportunityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    description: str | None
    category: str | None
    target_market: str | None
    target_customer: str | None
    business_model: str
    monetization_method: str | None
    status: str
    score: int | None
    confidence_score: int | None
    risk_level: str
    time_to_validate_days: int | None
    data_origin: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    last_evaluated: datetime | None = None
    estimated_setup_cost: Decimal | None = None
    estimated_monthly_cost: Decimal | None = None
    estimated_monthly_profit: Decimal | None = None
    estimated_roi: Decimal | None = None
    estimate_currency: str | None = None


class OpportunityListResponse(BaseModel):
    items: list[OpportunityResponse]
    total: int
    limit: int
    offset: int


class EvidenceCreate(BaseModel):
    source_url: str | None = Field(default=None, max_length=2048)
    source_name: str = Field(min_length=1, max_length=200)
    source_type: str = Field(min_length=1, max_length=100)
    evidence_type: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=5000)
    captured_at: datetime
    confidence: ScoreInput | None = None

    @field_validator("source_url")
    @classmethod
    def safe_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("source_url must be an absolute http(s) URL without credentials")
        return value

    @field_validator("captured_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("captured_at must include a timezone")
        return value


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    opportunity_id: UUID
    source_url: str | None
    source_name: str
    source_type: str
    evidence_type: str
    summary: str
    captured_at: datetime
    confidence: int | None
    verification_status: str
    created_at: datetime


class EstimateCreate(BaseModel):
    scenario: Literal["PESSIMISTIC", "BASE", "OPTIMISTIC"]
    currency: str = Field(min_length=3, max_length=3)
    setup_cost: Money | None = None
    monthly_operating_cost: Money | None = None
    expected_monthly_revenue: Money | None = None
    assumptions_json: dict[str, Any] = Field(default_factory=dict)
    confidence_score: ScoreInput | None = None
    evaluated_at: datetime

    @field_validator("currency")
    @classmethod
    def normalized_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("evaluated_at")
    @classmethod
    def estimate_timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("evaluated_at must include a timezone")
        return value


class EstimateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    opportunity_id: UUID
    scenario: str
    currency: str
    setup_cost: Decimal | None
    monthly_operating_cost: Decimal | None
    expected_monthly_revenue: Decimal | None
    expected_monthly_profit: Decimal | None
    expected_roi: Decimal | None
    break_even_months: Decimal | None
    confidence_score: int | None
    assumptions_json: dict[str, Any]
    evaluated_at: datetime


class ScoreInputs(BaseModel):
    market_demand: ScoreInput
    monetization_potential: ScoreInput
    automation_feasibility: ScoreInput
    experiment_cost: ScoreInput
    competitive_advantage: ScoreInput
    scalability: ScoreInput
    evidence_confidence: ScoreInput


class OpportunityEvaluate(BaseModel):
    scoring_version: Literal["2026.11.1"] = "2026.11.1"
    scores: ScoreInputs
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "SEVERE"]
    disqualifiers: list[Literal["SEVERE_LEGAL_RISK", "SEVERE_COPYRIGHT_RISK", "SEVERE_PLATFORM_POLICY_VIOLATION", "FRAUD_INDICATOR", "PROHIBITED_OPERATION"]] = Field(default_factory=list)
    risk_assessment: str | None = Field(default=None, max_length=1000)


class ScoreDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    opportunity_id: UUID
    scoring_version: str
    market_demand_score: Decimal
    monetization_score: Decimal
    automation_score: Decimal
    cost_efficiency_score: Decimal
    competitive_advantage_score: Decimal
    scalability_score: Decimal
    evidence_confidence_score: Decimal
    total_score: Decimal
    disqualified: bool
    disqualification_reason: str | None
    created_at: datetime


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    opportunity_id: UUID
    scoring_version: str
    input_snapshot_json: dict[str, Any]
    result_snapshot_json: dict[str, Any]
    evaluated_by: str
    evaluated_at: datetime


class EvaluationResult(BaseModel):
    opportunity: OpportunityResponse
    score: ScoreDetailResponse
    evaluation: EvaluationResponse
    recommendation: str


class CompareRequest(BaseModel):
    opportunity_ids: list[UUID] = Field(min_length=2, max_length=5)
    scenario: Literal["PESSIMISTIC", "BASE", "OPTIMISTIC"] = "BASE"

    @model_validator(mode="after")
    def unique_ids(self) -> "CompareRequest":
        if len(set(self.opportunity_ids)) != len(self.opportunity_ids):
            raise ValueError("opportunity_ids must be unique")
        return self


class ComparisonItem(BaseModel):
    currency: str | None = None
    opportunity: OpportunityResponse
    scenario: str
    setup_cost: Decimal | None
    monthly_operating_cost: Decimal | None
    expected_monthly_revenue: Decimal | None
    expected_monthly_profit: Decimal | None
    expected_roi: Decimal | None
    break_even_months: Decimal | None
    automation_score: Decimal | None
    ranking: int
    reasons: list[str]


class CompareResponse(BaseModel):
    items: list[ComparisonItem]
    disclaimer: str


class RankingsResponse(BaseModel):
    items: list[OpportunityResponse]
    total: int


def rounded(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
