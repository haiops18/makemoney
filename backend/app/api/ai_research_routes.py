"""Owner research drafts and manual untrusted evidence; no automated research."""
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.opportunity_routes import _commit_or_conflict, _idempotent, _store_idempotency
from app.api.workflow_schemas import WorkflowResponse
from app.auth.dependencies import require_owner
from app.db.models import Agent, AIResearchRun, AIResearchSource, AuditEvent, Workflow, WorkflowEvent, WorkflowTask
from app.db.session import get_db

router = APIRouter(prefix='/api/v1/ai/research', dependencies=[Depends(require_owner)], tags=['ai-research'])


class ResearchCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    objective: str = Field(min_length=1, max_length=4000)
    category: str | None = Field(default=None, max_length=150)
    target_market: str | None = Field(default=None, max_length=200)
    target_customers: str | None = Field(default=None, max_length=500)
    max_cost_usd: Decimal = Field(gt=0, le=45, max_digits=18, decimal_places=6)

    @field_validator('max_cost_usd', mode='before')
    @classmethod
    def reject_float_money(cls, value):
        if isinstance(value, float):
            raise ValueError('Use a decimal string for money')
        return value


class ResearchResponse(ResearchCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class SourceCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    source_name: str = Field(min_length=1, max_length=200)
    source_url: str | None = Field(default=None, max_length=2048)
    excerpt: str = Field(min_length=1, max_length=12000)

    @field_validator('source_url')
    @classmethod
    def safe_syntax(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parts = urlsplit(value)
            if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password or any(ord(char) < 32 for char in value):
                raise ValueError
            _ = parts.port
        except ValueError:
            raise ValueError('Invalid source URL') from None
        return value


class SourceResponse(SourceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    research_run_id: UUID
    verification_status: str
    created_at: datetime


class ResearchWorkflowCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)


def _run(db: Session, run_id: UUID, lock: bool = False) -> AIResearchRun:
    statement = select(AIResearchRun).where(AIResearchRun.id == run_id)
    if lock:
        statement = statement.with_for_update()
    run = db.scalar(statement)
    if run is None:
        raise HTTPException(status_code=404, detail='Research draft not found')
    return run


@router.get('', response_model=list[ResearchResponse])
def list_research(limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    return list(db.scalars(select(AIResearchRun).order_by(AIResearchRun.created_at.desc(), AIResearchRun.id).offset(offset).limit(limit)))


@router.post('', response_model=ResearchResponse, status_code=201)
def create_research(body: ResearchCreate, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path, payload = '/api/v1/ai/research', body.model_dump(mode='json')
    existing = _idempotent(db, actor, key, 'POST', path, payload, ResearchResponse)
    if existing:
        return existing
    run = AIResearchRun(**body.model_dump(), created_by=actor, status='DRAFT')
    db.add(run)
    db.flush()
    result = ResearchResponse.model_validate(run)
    db.add(AuditEvent(actor=actor, action='ai_research.draft_created', entity_type='ai_research_run', entity_id=run.id, detail={'max_cost_usd': str(run.max_cost_usd)}))
    _store_idempotency(db, actor, key, 'POST', path, payload, result, 201)
    return _commit_or_conflict(db, actor, key, 'POST', path, payload, ResearchResponse, response) or result


@router.get('/{run_id}', response_model=ResearchResponse)
def get_research(run_id: UUID, db: Session = Depends(get_db)):
    return _run(db, run_id)


@router.get('/{run_id}/sources', response_model=list[SourceResponse])
def list_sources(run_id: UUID, limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    _run(db, run_id)
    return list(db.scalars(select(AIResearchSource).where(AIResearchSource.research_run_id == run_id).order_by(AIResearchSource.created_at, AIResearchSource.id).offset(offset).limit(limit)))


@router.post('/{run_id}/sources', response_model=SourceResponse, status_code=201)
def add_source(run_id: UUID, body: SourceCreate, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path, payload = f'/api/v1/ai/research/{run_id}/sources', body.model_dump(mode='json')
    existing = _idempotent(db, actor, key, 'POST', path, payload, SourceResponse)
    if existing:
        return existing
    _run(db, run_id, lock=True)
    source = AIResearchSource(research_run_id=run_id, **body.model_dump(), verification_status='UNVERIFIED')
    db.add(source)
    db.flush()
    result = SourceResponse.model_validate(source)
    db.add(AuditEvent(actor=actor, action='ai_research.source_added', entity_type='ai_research_source', entity_id=source.id, detail={'research_run_id': str(run_id), 'verification_status': 'UNVERIFIED'}))
    _store_idempotency(db, actor, key, 'POST', path, payload, result, 201)
    return _commit_or_conflict(db, actor, key, 'POST', path, payload, SourceResponse, response) or result


@router.post('/{run_id}/workflow', response_model=WorkflowResponse, status_code=201)
def create_research_workflow(run_id: UUID, body: ResearchWorkflowCreate, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path, payload = f'/api/v1/ai/research/{run_id}/workflow', body.model_dump(mode='json')
    existing = _idempotent(db, actor, key, 'POST', path, payload, WorkflowResponse)
    if existing:
        return existing
    run = _run(db, run_id, lock=True)
    if run.status != 'DRAFT':
        raise HTTPException(status_code=409, detail='Research draft is not eligible')
    if db.scalar(select(Workflow.id).where(Workflow.research_run_id == run_id)):
        raise HTTPException(status_code=409, detail='Research draft already has a workflow')
    role = db.scalar(select(Agent).where(Agent.role == 'research', Agent.enabled.is_(True)).with_for_update())
    if role is None:
        raise HTTPException(status_code=409, detail='Research role is unavailable')
    workflow = Workflow(research_run_id=run.id, opportunity_id=None, name=body.name, created_by=actor, version=2)
    db.add(workflow)
    db.flush()
    task = WorkflowTask(workflow_id=workflow.id, name='Validate research draft', task_type='VALIDATE_RESEARCH_DRAFT',
                        assigned_role=role.role, input_json={}, max_retries=0, timeout_seconds=30)
    db.add(task)
    db.flush()
    db.add_all([
        AuditEvent(actor=actor, action='workflow.created', entity_type='workflow', entity_id=workflow.id, detail={'research_run_id': str(run.id)}),
        AuditEvent(actor=actor, action='workflow.task_created', entity_type='workflow_task', entity_id=task.id, detail={'workflow_id': str(workflow.id)}),
        WorkflowEvent(workflow_id=workflow.id, event_type='CREATED', new_status='DRAFT', actor=actor, metadata_json={'research_run_id': str(run.id)}),
        WorkflowEvent(workflow_id=workflow.id, task_id=task.id, event_type='TASK_CREATED', new_status='PENDING', actor=actor, metadata_json={}),
    ])
    result = WorkflowResponse.model_validate(workflow).model_copy(update={'task_count': 1})
    _store_idempotency(db, actor, key, 'POST', path, payload, result, 201)
    return _commit_or_conflict(db, actor, key, 'POST', path, payload, WorkflowResponse, response) or result


@router.get('/{run_id}/workflow', response_model=WorkflowResponse)
def get_research_workflow(run_id: UUID, db: Session = Depends(get_db)):
    _run(db, run_id)
    workflow = db.scalar(select(Workflow).where(Workflow.research_run_id == run_id))
    if workflow is None:
        raise HTTPException(status_code=404, detail='Research workflow not found')
    from app.api.workflow_routes import workflow_response
    return workflow_response(db, workflow)
