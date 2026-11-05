"""Owner research drafts, manual evidence verification, AI stage pipelines and results.

Creating a pipeline never runs it: every AI task still needs a workflow approval,
its own action approval, global consent and a budget reservation."""
from datetime import UTC, datetime
from typing import Literal
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.opportunity_routes import _commit_or_conflict, _idempotent, _store_idempotency
from app.api.workflow_schemas import WorkflowResponse
from app.auth.dependencies import require_owner
from app.ai_brain.execution import AI_TASK_PROMPTS, AI_TASK_ROLES
from app.db.models import Agent, AIAgentProfile, AIInvocation, AIModelPrice, AIPromptVersion, AIResearchRun, AIResearchSource, AuditEvent, BudgetReservation, Opportunity, OpportunityEvidence, TaskDependency, TaskExecution, Workflow, WorkflowEvent, WorkflowTask
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
    opportunity_id: UUID | None = None
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
    verified_by: str | None = None
    verified_at: datetime | None = None
    verification_note: str | None = None
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


class SourceVerification(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    status: Literal['VERIFIED', 'REJECTED']
    note: str = Field(min_length=1, max_length=1000)


def _active_dispatch(db: Session, run_id: UUID) -> bool:
    return bool(db.scalar(select(func.count()).select_from(AIInvocation).where(AIInvocation.research_run_id == run_id, AIInvocation.status.in_(['PREPARED', 'DISPATCHED']))))


@router.post('/{run_id}/sources/{source_id}/verification', response_model=SourceResponse)
def verify_source(run_id: UUID, source_id: UUID, body: SourceVerification, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Record the Owner's own verification of an excerpt; the server never fetches it.

    Only VERIFIED sources may support a FACT. A decision is final; changes to a
    source alter the action hash, so any approval prepared earlier no longer applies.
    """
    path, payload = f'/api/v1/ai/research/{run_id}/sources/{source_id}/verification', body.model_dump(mode='json')
    existing = _idempotent(db, actor, key, 'POST', path, payload, SourceResponse)
    if existing:
        return existing
    _run(db, run_id, lock=True)
    source = db.scalar(select(AIResearchSource).where(AIResearchSource.id == source_id, AIResearchSource.research_run_id == run_id).with_for_update())
    if source is None:
        raise HTTPException(status_code=404, detail='Research source not found')
    if source.verification_status != 'UNVERIFIED':
        raise HTTPException(status_code=409, detail='Source verification has already been decided')
    if _active_dispatch(db, run_id):
        raise HTTPException(status_code=409, detail='An AI invocation for this research is in progress')
    source.verification_status, source.verified_by, source.verified_at, source.verification_note = body.status, actor, datetime.now(UTC), body.note
    db.flush()
    result = SourceResponse.model_validate(source)
    db.add(AuditEvent(actor=actor, action='ai_research.source_verified', entity_type='ai_research_source', entity_id=source.id,
                      detail={'research_run_id': str(run_id), 'verification_status': body.status}))
    _store_idempotency(db, actor, key, 'POST', path, payload, result, 200)
    return _commit_or_conflict(db, actor, key, 'POST', path, payload, SourceResponse, response) or result


# Stage DAG: plan → (market, competitor) → opportunity → (financial, risk) → report.
PIPELINE = [('AI_RESEARCH_PLAN', 'Research plan', []), ('AI_MARKET_RESEARCH', 'Market research', ['AI_RESEARCH_PLAN']),
            ('AI_COMPETITOR_ANALYSIS', 'Competitor analysis', ['AI_RESEARCH_PLAN']),
            ('AI_OPPORTUNITY_GENERATION', 'Opportunity generation', ['AI_MARKET_RESEARCH', 'AI_COMPETITOR_ANALYSIS']),
            ('AI_FINANCIAL_ANALYSIS', 'Financial analysis', ['AI_OPPORTUNITY_GENERATION']),
            ('AI_RISK_REVIEW', 'Risk review', ['AI_OPPORTUNITY_GENERATION']),
            ('AI_RESEARCH_REPORT', 'Research report', ['AI_FINANCIAL_ANALYSIS', 'AI_RISK_REVIEW'])]


class PipelineCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirm_no_execution: Literal[True]


class PipelineTask(BaseModel):
    id: UUID
    task_type: str
    assigned_role: str
    prompt_version: str
    price_version: str
    model_id: str
    depends_on: list[UUID]


class PipelineResponse(BaseModel):
    workflow_id: UUID
    tasks: list[PipelineTask]


def _stage_inputs(db: Session, task_type: str, now: datetime) -> tuple[AIAgentProfile, AIModelPrice, AIPromptVersion]:
    role = AI_TASK_ROLES[task_type]
    agent = db.scalar(select(Agent).where(Agent.role == role, Agent.enabled.is_(True)))
    profile = db.scalar(select(AIAgentProfile).where(AIAgentProfile.agent_id == agent.id)) if agent else None
    if profile is None or not profile.enabled:
        raise HTTPException(status_code=409, detail=f'An enabled AI profile is required for the {role} agent')
    price = db.scalar(select(AIModelPrice).where(AIModelPrice.provider_id == profile.provider_id, AIModelPrice.model_id == profile.model_id,
                                                  AIModelPrice.effective_at <= now, (AIModelPrice.expires_at.is_(None)) | (AIModelPrice.expires_at > now))
                      .order_by(AIModelPrice.effective_at.desc(), AIModelPrice.created_at.desc()).limit(1))
    if price is None:
        raise HTTPException(status_code=409, detail=f'An effective model price is required for {profile.model_id}')
    candidates = db.scalars(select(AIPromptVersion).where(AIPromptVersion.name == AI_TASK_PROMPTS[task_type]).order_by(AIPromptVersion.created_at.desc(), AIPromptVersion.id))
    prompt = next((item for item in candidates if item.constraints_json.get('provider_execution') is True and item.constraints_json.get('tools') == []
                   and item.constraints_json.get('external_actions') is False), None)
    if prompt is None:
        raise HTTPException(status_code=409, detail='An execution-enabled prompt version is unavailable')
    return profile, price, prompt


@router.post('/{run_id}/pipeline', response_model=PipelineResponse, status_code=201)
def create_pipeline(run_id: UUID, body: PipelineCreate, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Add the standard AI stage tasks to a draft research workflow. Nothing runs."""
    path, payload = f'/api/v1/ai/research/{run_id}/pipeline', body.model_dump(mode='json')
    existing = _idempotent(db, actor, key, 'POST', path, payload, PipelineResponse)
    if existing:
        return existing
    _run(db, run_id, lock=True)
    workflow = db.scalar(select(Workflow).where(Workflow.research_run_id == run_id).with_for_update())
    if workflow is None or workflow.status != 'DRAFT':
        raise HTTPException(status_code=409, detail='A draft research workflow is required')
    tasks = list(db.scalars(select(WorkflowTask).where(WorkflowTask.workflow_id == workflow.id).order_by(WorkflowTask.created_at, WorkflowTask.id)))
    if any(task.task_type in AI_TASK_ROLES for task in tasks):
        raise HTTPException(status_code=409, detail='The research workflow already contains AI tasks')
    if len(tasks) + len(PIPELINE) > 100:
        raise HTTPException(status_code=409, detail='A workflow may contain at most 100 tasks')
    now = datetime.now(UTC)
    created: dict[str, WorkflowTask] = {}
    items = []
    for task_type, name, parents in PIPELINE:
        profile, price, prompt = _stage_inputs(db, task_type, now)
        task = WorkflowTask(workflow_id=workflow.id, name=name, task_type=task_type, assigned_role=AI_TASK_ROLES[task_type],
                            input_json={'ai_price_id': str(price.id), 'ai_prompt_version_id': str(prompt.id)},
                            max_retries=0, timeout_seconds=min(profile.timeout_seconds, 300))
        db.add(task)
        db.flush()
        # The first stage waits for the deterministic draft validation task(s).
        dependency_ids = [created[parent].id for parent in parents] if parents else [item.id for item in tasks]
        for dependency_id in dependency_ids:
            db.add(TaskDependency(workflow_id=workflow.id, task_id=task.id, depends_on_task_id=dependency_id))
        created[task_type] = task
        db.add(AuditEvent(actor=actor, action='workflow.task_created', entity_type='workflow_task', entity_id=task.id,
                          detail={'workflow_id': str(workflow.id), 'task_type': task_type, 'prompt_version_id': str(prompt.id), 'price_id': str(price.id)}))
        db.add(WorkflowEvent(workflow_id=workflow.id, task_id=task.id, event_type='TASK_CREATED', new_status='PENDING', actor=actor, metadata_json={'task_type': task_type}))
        items.append(PipelineTask(id=task.id, task_type=task_type, assigned_role=task.assigned_role, prompt_version=prompt.version,
                                  price_version=price.version, model_id=profile.model_id, depends_on=dependency_ids))
    db.flush()
    result = PipelineResponse(workflow_id=workflow.id, tasks=items)
    _store_idempotency(db, actor, key, 'POST', path, payload, result, 201)
    return _commit_or_conflict(db, actor, key, 'POST', path, payload, PipelineResponse, response) or result


class StageResult(BaseModel):
    task_id: UUID
    name: str
    task_type: str
    assigned_role: str
    task_status: str
    invocation_id: UUID | None = None
    invocation_status: str | None = None
    model_id: str | None = None
    error_code: str | None = None
    estimated_cost: str | None = None
    calculated_cost: str | None = None
    confirmed_cost: str | None = None
    output: dict | None = None
    completed_at: datetime | None = None


class ResearchResults(BaseModel):
    research_run_id: UUID
    workflow_id: UUID | None
    workflow_status: str | None
    opportunity_id: UUID | None
    ai_generated: Literal[True] = True
    stages: list[StageResult]


def _results(db: Session, run: AIResearchRun) -> ResearchResults:
    workflow = db.scalar(select(Workflow).where(Workflow.research_run_id == run.id))
    stages = []
    if workflow is not None:
        for task in db.scalars(select(WorkflowTask).where(WorkflowTask.workflow_id == workflow.id).order_by(WorkflowTask.created_at, WorkflowTask.id)):
            if task.task_type not in AI_TASK_ROLES:
                continue
            row = db.execute(select(AIInvocation, BudgetReservation).join(TaskExecution, TaskExecution.id == AIInvocation.execution_id)
                             .outerjoin(BudgetReservation, BudgetReservation.id == AIInvocation.reservation_id)
                             .where(TaskExecution.task_id == task.id).order_by(TaskExecution.attempt_number.desc()).limit(1)).first()
            item = StageResult(task_id=task.id, name=task.name, task_type=task.task_type, assigned_role=task.assigned_role, task_status=task.status)
            if row is not None:
                invocation, reservation = row
                confirmed = reservation.actual_amount if reservation is not None and reservation.status in {'SETTLED', 'RELEASED'} else None
                item = item.model_copy(update={'invocation_id': invocation.id, 'invocation_status': invocation.status, 'model_id': invocation.model_id,
                                               'error_code': invocation.error_code, 'estimated_cost': str(invocation.estimated_cost),
                                               'calculated_cost': None if invocation.calculated_cost is None else str(invocation.calculated_cost),
                                               'confirmed_cost': None if confirmed is None else str(confirmed),
                                               'output': invocation.output_json if invocation.status == 'SUCCEEDED' else None, 'completed_at': invocation.completed_at})
            stages.append(item)
    order = {task_type: index for index, (task_type, _, _) in enumerate(PIPELINE)}
    stages.sort(key=lambda stage: order.get(stage.task_type, len(order)))
    return ResearchResults(research_run_id=run.id, workflow_id=workflow.id if workflow else None, workflow_status=workflow.status if workflow else None,
                           opportunity_id=run.opportunity_id, stages=stages)


@router.get('/{run_id}/results', response_model=ResearchResults)
def research_results(run_id: UUID, db: Session = Depends(get_db)):
    """Model output is untrusted analysis, not verified market fact."""
    return _results(db, _run(db, run_id))


class PromoteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    business_model: str = Field(min_length=1, max_length=100)
    monetization_method: str | None = Field(default=None, max_length=200)

    @field_validator('business_model', mode='before')
    @classmethod
    def normalized_identifier(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class PromoteResponse(BaseModel):
    research_run_id: UUID
    opportunity_id: UUID
    evidence_count: int


AI_DISCLAIMER = 'AI-generated research draft; model output is unverified and is not market fact.'


@router.post('/{run_id}/promote', response_model=PromoteResponse, status_code=201)
def promote_research(run_id: UUID, body: PromoteRequest, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Create one DRAFT opportunity from a completed research workflow.

    Only Owner-entered sources become evidence (with their own verification
    status). AI findings stay in the research record and are labelled unverified.
    Scoring and evaluation remain the Opportunity Engine's Owner-driven steps.
    """
    path, payload = f'/api/v1/ai/research/{run_id}/promote', body.model_dump(mode='json')
    existing = _idempotent(db, actor, key, 'POST', path, payload, PromoteResponse)
    if existing:
        return existing
    run = _run(db, run_id, lock=True)
    if run.opportunity_id is not None:
        raise HTTPException(status_code=409, detail='Research has already been promoted')
    workflow = db.scalar(select(Workflow).where(Workflow.research_run_id == run_id).with_for_update())
    results = _results(db, run)
    report = next((stage for stage in reversed(results.stages) if stage.task_type == 'AI_RESEARCH_REPORT' and stage.output), None)
    if workflow is None or workflow.status != 'COMPLETED' or report is None:
        raise HTTPException(status_code=409, detail='A completed research workflow with a report is required')
    description = f"{AI_DISCLAIMER}\n\n{report.output['summary']}"[:5000]
    opportunity = Opportunity(title=body.title, description=description, category=run.category[:100] if run.category else None, target_market=run.target_market,
                              target_customer=run.target_customers, business_model=body.business_model, monetization_method=body.monetization_method,
                              status='DRAFT', data_origin='AI_RESEARCH', created_by=actor)
    db.add(opportunity)
    db.flush()
    sources = list(db.scalars(select(AIResearchSource).where(AIResearchSource.research_run_id == run_id, AIResearchSource.verification_status != 'REJECTED')
                              .order_by(AIResearchSource.created_at, AIResearchSource.id)))
    for source in sources:
        db.add(OpportunityEvidence(opportunity_id=opportunity.id, source_url=source.source_url, source_name=source.source_name,
                                   source_type='OWNER_RESEARCH_SOURCE', evidence_type=f'RESEARCH_SOURCE:{source.id}', summary=source.excerpt[:5000],
                                   captured_at=source.created_at, verification_status=source.verification_status))
    run.opportunity_id = opportunity.id
    db.flush()
    result = PromoteResponse(research_run_id=run.id, opportunity_id=opportunity.id, evidence_count=len(sources))
    db.add(AuditEvent(actor=actor, action='ai_research.promoted', entity_type='ai_research_run', entity_id=run.id,
                      detail={'opportunity_id': str(opportunity.id), 'evidence_count': len(sources), 'report_invocation_id': str(report.invocation_id)}))
    db.add(AuditEvent(actor=actor, action='opportunity.created', entity_type='opportunity', entity_id=opportunity.id,
                      detail={'business_model': opportunity.business_model, 'data_origin': 'AI_RESEARCH'}))
    _store_idempotency(db, actor, key, 'POST', path, payload, result, 201)
    return _commit_or_conflict(db, actor, key, 'POST', path, payload, PromoteResponse, response) or result
