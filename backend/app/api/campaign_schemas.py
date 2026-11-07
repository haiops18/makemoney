"""Step 7A campaign API contracts. Money uses decimal strings; URLs are syntax-checked only."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from app.campaigns.links import LinkRuleError, normalize_hosts, normalize_keys, safe_url

CampaignStatus = Literal['DRAFT', 'ACTIVE', 'PAUSED', 'ARCHIVED']
Network = Literal['SHOPEE', 'TIKTOK_SHOP', 'ACCESSTRADE', 'ECOMOBI', 'LAZADA', 'OTHER']
Term = Literal['JOIN_CONDITIONS', 'COMMISSION_MODEL', 'COMMISSION_RATE', 'COMMISSION_CAP', 'COOKIE_DAYS', 'ATTRIBUTION', 'PAYOUT', 'REFUND_CANCELLATION', 'TAX_WITHHOLDING']
Unit = Literal['NONE', 'PERCENT', 'VND', 'USD', 'DAYS']


def _no_float(value):
    if isinstance(value, float):
        raise ValueError('Use a decimal string for numbers')
    return value


def _url(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return safe_url(value)
    except LinkRuleError as exc:
        raise ValueError(str(exc)) from None


NoFloat = BeforeValidator(_no_float)
WebUrl = Annotated[str | None, AfterValidator(_url)]


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class CampaignFields(Strict):
    name: str = Field(min_length=1, max_length=200)
    niche: str | None = Field(default=None, max_length=200)
    target_audience: str | None = Field(default=None, max_length=500)
    goal: str | None = Field(default=None, max_length=2000)
    language: Literal['vi', 'en'] = 'vi'
    disclosure_text: str | None = Field(default=None, min_length=1, max_length=500)
    max_cost_usd: Annotated[Decimal, NoFloat] = Field(gt=0, le=45, max_digits=18, decimal_places=6)


class CampaignCreate(CampaignFields):
    opportunity_id: UUID


class CampaignUpdate(Strict):
    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    niche: str | None = Field(default=None, max_length=200)
    target_audience: str | None = Field(default=None, max_length=500)
    goal: str | None = Field(default=None, max_length=2000)
    language: Literal['vi', 'en'] | None = None
    disclosure_text: str | None = Field(default=None, max_length=500)
    max_cost_usd: Annotated[Decimal | None, NoFloat] = Field(default=None, gt=0, le=45, max_digits=18, decimal_places=6)


class CampaignStatusChange(Strict):
    version: int = Field(ge=1)
    status: CampaignStatus


class CampaignResponse(CampaignFields):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    opportunity_id: UUID
    business_model: str
    status: str
    version: int
    created_by: str
    created_at: datetime
    updated_at: datetime


class SourceCreate(Strict):
    source_name: str = Field(min_length=1, max_length=200)
    source_url: WebUrl = Field(default=None, max_length=2048)
    excerpt: str = Field(min_length=1, max_length=12000)
    captured_at: datetime

    @field_validator('captured_at')
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError('captured_at needs a timezone')
        return value


class SourceVerification(Strict):
    status: Literal['VERIFIED', 'REJECTED']
    note: str = Field(min_length=1, max_length=1000)


class SourceResponse(Strict):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    campaign_id: UUID
    source_name: str
    source_url: str | None
    excerpt: str
    captured_at: datetime
    verification_status: str
    verified_by: str | None = None
    verified_at: datetime | None = None
    verification_note: str | None = None
    created_at: datetime


class ProgramCreate(Strict):
    network: Network
    name: str = Field(min_length=1, max_length=200)
    join_url: WebUrl = Field(default=None, max_length=2048)
    link_hosts: list[str] = Field(min_length=1, max_length=10)
    tracking_param_keys: list[str] = Field(default_factory=list, max_length=10)

    @field_validator('link_hosts')
    @classmethod
    def hosts(cls, value: list[str]) -> list[str]:
        try:
            return normalize_hosts(value)
        except LinkRuleError as exc:
            raise ValueError(str(exc)) from None

    @field_validator('tracking_param_keys')
    @classmethod
    def keys(cls, value: list[str]) -> list[str]:
        try:
            return normalize_keys(value)
        except LinkRuleError as exc:
            raise ValueError(str(exc)) from None


class TermCreate(Strict):
    term: Term
    value_text: str = Field(min_length=1, max_length=1000)
    value_numeric: Annotated[Decimal | None, NoFloat] = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    unit: Unit = 'NONE'
    source_id: UUID | None = None

    @model_validator(mode='after')
    def numeric_has_unit(self):
        if (self.value_numeric is None) != (self.unit == 'NONE'):
            raise ValueError('A numeric value needs a unit, and a unit needs a numeric value')
        if self.unit == 'PERCENT' and self.value_numeric is not None and self.value_numeric > 100:
            raise ValueError('A percentage cannot exceed 100')
        return self


class TermResponse(TermCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    program_id: UUID
    evidence_status: Literal['VERIFIED', 'UNVERIFIED', 'REJECTED', 'UNSOURCED']
    created_by: str
    created_at: datetime


class ProgramResponse(Strict):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    campaign_id: UUID
    network: str
    name: str
    join_url: str | None
    link_hosts: list[str]
    tracking_param_keys: list[str]
    terms: list[TermResponse] = Field(default_factory=list)
    created_by: str
    created_at: datetime


class ProductCreate(Strict):
    name: str = Field(min_length=1, max_length=300)
    merchant: str | None = Field(default=None, max_length=200)
    product_url: WebUrl = Field(default=None, max_length=2048)
    price_text: str | None = Field(default=None, min_length=1, max_length=100)
    price_source_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def price_needs_source(self):
        if self.price_text is not None and self.price_source_id is None:
            raise ValueError('A price needs a source')
        return self


class ProductResponse(ProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    campaign_id: UUID
    price_evidence_status: Literal['VERIFIED', 'UNVERIFIED', 'REJECTED', 'UNSOURCED']
    created_by: str
    created_at: datetime


class LinkCreate(Strict):
    program_id: UUID
    product_id: UUID | None = None
    label: str = Field(min_length=1, max_length=200)
    original_url: str = Field(min_length=1, max_length=2048)
    tracking_params: dict[str, str] = Field(default_factory=dict, max_length=10)


class LinkResponse(Strict):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    campaign_id: UUID
    program_id: UUID
    product_id: UUID | None
    label: str
    original_url: str
    tracking_params: dict[str, str]
    final_url: str
    status: str
    created_by: str
    created_at: datetime
    retired_at: datetime | None = None
