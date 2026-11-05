"""Owner configuration of agent models; this module cannot invoke a provider."""
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.opportunity_routes import _commit_or_conflict, _idempotent, _store_idempotency
from app.auth.dependencies import require_owner
from app.db.models import Agent, AIAgentProfile, AIProvider, AuditEvent
from app.db.session import get_db

router = APIRouter(prefix='/api/v1/ai/agent-profiles', dependencies=[Depends(require_owner)], tags=['ai-agent-profiles'])


class ProfileSet(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    provider_id: UUID
    model_id: str = Field(min_length=1, max_length=200)
    max_output_tokens: int = Field(ge=1, le=100000)
    temperature: Decimal | None = Field(default=None, ge=0, le=2, max_digits=3, decimal_places=2)
    timeout_seconds: int = Field(ge=1, le=300)
    max_cost_usd: Decimal = Field(gt=0, le=45, max_digits=18, decimal_places=6)
    enabled: bool = False

    @field_validator('max_cost_usd', mode='before')
    @classmethod
    def reject_float_money(cls, value):
        if isinstance(value, float):
            raise ValueError('Use a decimal string for money')
        return value


class ProfileResponse(ProfileSet):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    agent_id: UUID


@router.get('', response_model=list[ProfileResponse])
def list_profiles(db: Session = Depends(get_db)):
    return list(db.scalars(select(AIAgentProfile).order_by(AIAgentProfile.created_at, AIAgentProfile.id)))


@router.put('/{agent_id}', response_model=ProfileResponse)
def set_profile(agent_id: UUID, body: ProfileSet, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path = f'/api/v1/ai/agent-profiles/{agent_id}'
    payload = body.model_dump(mode='json')
    existing = _idempotent(db, actor, key, 'PUT', path, payload, ProfileResponse)
    if existing:
        return existing
    agent = db.scalar(select(Agent).where(Agent.id == agent_id).with_for_update())
    provider = db.scalar(select(AIProvider).where(AIProvider.id == body.provider_id, AIProvider.archived.is_(False)).with_for_update())
    if agent is None or provider is None:
        raise HTTPException(status_code=404, detail='Agent or provider not found')
    profile = db.scalar(select(AIAgentProfile).where(AIAgentProfile.agent_id == agent_id).with_for_update())
    if profile is None:
        profile = AIAgentProfile(agent_id=agent_id, **body.model_dump())
        db.add(profile)
    else:
        for field, value in body.model_dump().items():
            setattr(profile, field, value)
    db.flush()
    result = ProfileResponse.model_validate(profile)
    db.add(AuditEvent(actor=actor, action='ai_agent_profile.configured', entity_type='ai_agent_profile', entity_id=profile.id,
                      detail={'agent_id': str(agent.id), 'provider_id': str(provider.id), 'model_id': profile.model_id, 'enabled': profile.enabled}))
    _store_idempotency(db, actor, key, 'PUT', path, payload, result, 200)
    return _commit_or_conflict(db, actor, key, 'PUT', path, payload, ProfileResponse, response) or result
