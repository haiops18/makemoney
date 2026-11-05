"""Versioned Owner-supplied pricing records. They do not enable provider calls."""
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.opportunity_routes import _commit_or_conflict, _idempotent, _store_idempotency
from app.ai_brain.pricing import Pricing
from app.auth.dependencies import require_owner
from app.db.models import AIModelPrice, AIProvider, AuditEvent
from app.db.session import get_db

router = APIRouter(prefix='/api/v1/ai/providers', dependencies=[Depends(require_owner)], tags=['ai-pricing'])


class PriceCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)
    model_id: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    currency: Literal['USD'] = 'USD'
    input_per_million: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    output_per_million: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    effective_at: datetime
    expires_at: datetime | None = None
    source_note: str = Field(min_length=1, max_length=500)

    @field_validator('input_per_million', 'output_per_million', mode='before')
    @classmethod
    def reject_float_money(cls, value):
        if isinstance(value, float):
            raise ValueError('Use a decimal string for money')
        return value

    @field_validator('effective_at', 'expires_at')
    @classmethod
    def timezone_required(cls, value: datetime | None):
        if value is not None and value.utcoffset() is None:
            raise ValueError('Timestamp must include a timezone')
        return value

    @model_validator(mode='after')
    def valid_period(self):
        if self.expires_at is not None and self.expires_at <= self.effective_at:
            raise ValueError('Expiry must be after effective date')
        return self


class PriceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    provider_id: UUID
    model_id: str
    version: str
    currency: str
    input_per_million: Decimal
    output_per_million: Decimal
    effective_at: datetime
    expires_at: datetime | None
    source_note: str
    created_at: datetime


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    max_input_tokens: int = Field(ge=0, le=10_000_000)
    max_output_tokens: int = Field(ge=1, le=100_000)
    attempts: int = Field(default=1, ge=1, le=10)


class QuoteResponse(BaseModel):
    price_id: UUID
    model_id: str
    price_version: str
    estimated_ceiling_usd: Decimal
    disclaimer: str


def provider_or_404(db: Session, provider_id: UUID, lock: bool = False):
    statement = select(AIProvider).where(AIProvider.id == provider_id, AIProvider.archived.is_(False))
    if lock:
        statement = statement.with_for_update()
    result = db.scalar(statement)
    if result is None:
        raise HTTPException(status_code=404, detail='Provider not found')
    return result


@router.get('/{provider_id}/prices', response_model=list[PriceResponse])
def list_prices(provider_id: UUID, limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    provider_or_404(db, provider_id)
    return list(db.scalars(select(AIModelPrice).where(AIModelPrice.provider_id == provider_id).order_by(AIModelPrice.effective_at.desc(), AIModelPrice.id).offset(offset).limit(limit)))


@router.post('/{provider_id}/prices', response_model=PriceResponse, status_code=201)
def create_price(provider_id: UUID, body: PriceCreate, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path = f'/api/v1/ai/providers/{provider_id}/prices'
    payload = body.model_dump(mode='json')
    existing = _idempotent(db, actor, key, 'POST', path, payload, PriceResponse)
    if existing:
        return existing
    provider_or_404(db, provider_id, lock=True)
    price = AIModelPrice(provider_id=provider_id, **body.model_dump())
    db.add(price)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Pricing version already exists or conflicts') from None
    result = PriceResponse.model_validate(price)
    db.add(AuditEvent(actor=actor, action='ai_model_price.created', entity_type='ai_model_price', entity_id=price.id,
                      detail={'provider_id': str(provider_id), 'model_id': price.model_id, 'version': price.version}))
    _store_idempotency(db, actor, key, 'POST', path, payload, result, 201)
    return _commit_or_conflict(db, actor, key, 'POST', path, payload, PriceResponse, response) or result


@router.post('/{provider_id}/prices/{price_id}/quote', response_model=QuoteResponse)
def quote_price(provider_id: UUID, price_id: UUID, body: QuoteRequest, db: Session = Depends(get_db)):
    """Read-only estimate, not an approval, reservation or provider hard cap."""
    provider_or_404(db, provider_id)
    price = db.scalar(select(AIModelPrice).where(AIModelPrice.id == price_id, AIModelPrice.provider_id == provider_id))
    if price is None:
        raise HTTPException(status_code=404, detail='Price not found')
    effective = price.effective_at if price.effective_at.tzinfo else price.effective_at.replace(tzinfo=UTC)
    expires = price.expires_at if price.expires_at is None or price.expires_at.tzinfo else price.expires_at.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    if effective > now or (expires is not None and expires <= now):
        raise HTTPException(status_code=409, detail='Price version is not currently effective')
    pricing = Pricing(price.model_id, price.version, effective, Decimal(price.input_per_million), Decimal(price.output_per_million))
    return QuoteResponse(price_id=price.id, model_id=price.model_id, price_version=price.version,
                         estimated_ceiling_usd=pricing.ceiling(body.max_input_tokens, body.max_output_tokens, body.attempts),
                         disclaimer='Estimate only; provider charges may differ. No approval or reservation was granted.')
