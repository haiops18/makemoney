import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import AgentResponse, AgentUpdate, AuditEventResponse, DashboardResponse, MessageResponse
from app.auth.dependencies import require_owner
from app.core.config import Settings, get_settings
from app.db.models import Agent, AuditEvent, IdempotencyRecord
from app.db.session import get_db

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_owner)])


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> DashboardResponse:
    since = datetime.now(UTC) - timedelta(days=1)
    return DashboardResponse(
        agents_total=db.scalar(select(func.count()).select_from(Agent)) or 0,
        agents_enabled=db.scalar(select(func.count()).select_from(Agent).where(Agent.enabled.is_(True))) or 0,
        audit_events_last_24h=db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.timestamp >= since)) or 0,
        monthly_budget_usd=settings.monthly_budget_usd,
        timezone=settings.timezone,
    )


@router.get("/agents", response_model=list[AgentResponse])
def list_agents(db: Session = Depends(get_db)) -> list[Agent]:
    return list(db.scalars(select(Agent).order_by(Agent.role)))


@router.patch("/agents/{agent_id}", response_model=AgentResponse)
def update_agent(
    agent_id: UUID,
    update: AgentUpdate,
    response: Response,
    idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    actor: str = Depends(require_owner),
    db: Session = Depends(get_db),
) -> AgentResponse:
    path = f"/api/v1/agents/{agent_id}"
    body = update.model_dump(mode="json")
    request_hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    existing = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.actor == actor, IdempotencyRecord.key == idempotency_key))
    if existing:
        if (existing.method, existing.path, existing.request_hash) != ("PATCH", path, request_hash):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key was used for another request")
        response.status_code = existing.status_code
        return AgentResponse.model_validate(existing.response_body)

    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    agent.enabled = update.enabled
    db.flush()
    payload = AgentResponse.model_validate(agent).model_dump(mode="json")
    db.add(AuditEvent(actor=actor, action="agent.updated", entity_type="agent", entity_id=agent.id, detail=body))
    db.add(IdempotencyRecord(actor=actor, key=idempotency_key, method="PATCH", path=path, request_hash=request_hash, status_code=200, response_body=payload))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.actor == actor, IdempotencyRecord.key == idempotency_key))
        if existing and (existing.method, existing.path, existing.request_hash) == ("PATCH", path, request_hash):
            return AgentResponse.model_validate(existing.response_body)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key was used for another request")
    return AgentResponse.model_validate(payload)


@router.get("/audit-events", response_model=list[AuditEventResponse])
def list_audit_events(limit: int = 100, db: Session = Depends(get_db)) -> list[AuditEvent]:
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="limit must be between 1 and 100")
    return list(db.scalars(select(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(limit)))


@router.get("/settings", response_model=MessageResponse)
def settings_status() -> MessageResponse:
    return MessageResponse(message="External execution is disabled until approval, budget, and policy modules are installed.")

