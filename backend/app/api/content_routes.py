"""Step 7A content batches and drafts.

A content batch is a CONTENT research run holding a frozen snapshot of the campaign's
data, plus a workflow (validation → AI_CONTENT_DRAFT). Creating a batch runs nothing:
the Owner approves it with the existing one-approval auto-run (or per task), and every
AI call keeps consent, policy, cost-limit and budget-reservation checks.
"""
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_brain.content_contract import _WEB_ADDRESS, CONTENT_TYPES, MAX_ITEMS, ContentRequest, ContentType
from app.ai_brain.execution import AI_TASK_ROLES
from app.api.ai_research_routes import _stage_inputs
from app.api.campaign_routes import IdempotencyKey, _audit, _campaign, _save
from app.api.opportunity_routes import _idempotent
from app.auth.dependencies import require_owner
from app.db.models import (
    AffiliateLink, AffiliateProgram, AffiliateProgramTerm, AIInvocation, AIResearchRun, AIResearchSource, BudgetReservation, CampaignProduct,
    CampaignSource, ContentCheck, ContentItem, ContentPublishRecord, ContentVersion, Opportunity, TaskDependency, Workflow, WorkflowEvent, WorkflowTask,
)
from app.db.session import get_db

router = APIRouter(prefix='/api/v1/campaigns', dependencies=[Depends(require_owner)], tags=['campaign-content'])
MAX_SOURCES = 20


def _no_float(value):
    if isinstance(value, float):
        raise ValueError('Use a decimal string for money')
    return value


class BatchCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    affiliate_link_id: UUID
    content_types: list[ContentType] = Field(min_length=1, max_length=len(CONTENT_TYPES))
    count_per_type: int = Field(default=1, ge=1, le=3)
    max_cost_usd: Annotated[Decimal, BeforeValidator(_no_float)] = Field(gt=0, le=45, max_digits=18, decimal_places=6)

    @field_validator('content_types')
    @classmethod
    def unique_types(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError('Content types must be unique')
        return value

    @model_validator(mode='after')
    def total_items(self):
        if len(self.content_types) * self.count_per_type > MAX_ITEMS:
            raise ValueError(f'A batch may contain at most {MAX_ITEMS} items')
        return self


class BatchResponse(BaseModel):
    run_id: UUID
    workflow_id: UUID | None
    workflow_status: str | None
    content_types: list[str]
    count_per_type: int
    max_cost_usd: Decimal
    affiliate_link_id: UUID
    source_count: int
    item_count: int
    created_at: datetime


class VersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    version_no: int
    base_version_no: int | None
    title: str
    body: str
    hashtags: list[str]
    cta: str
    claims: list[dict[str, Any]]
    author_kind: str
    author: str
    created_at: datetime


class ContentResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    batch_run_id: UUID
    content_type: str
    language: str
    status: str
    product_id: UUID | None
    affiliate_link_id: UUID
    current_version: VersionResponse
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
    created_at: datetime
    updated_at: datetime


class CheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    check_name: str
    result: str
    method: str
    note: str
    evidence: list[str]
    attested_by: str | None = None
    attested_at: datetime | None = None


class PublishRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version_no: int
    channel: str
    published_url: str
    published_at: datetime
    recorded_by: str
    created_at: datetime


class ContentDetail(ContentResponse):
    versions: list[VersionResponse]
    checks: list[CheckResponse] = Field(default_factory=list)
    publish_records: list[PublishRecordResponse] = Field(default_factory=list)


class UsageLine(BaseModel):
    key: str
    invocations: int
    estimated_cost: Decimal
    calculated_cost: Decimal
    held_amount: Decimal


class CampaignUsage(BaseModel):
    currency: str = 'USD'
    max_cost_usd: Decimal
    batch_limits_total: Decimal
    invocations: int
    calculated_cost: Decimal
    held_amount: Decimal
    by_batch: list[UsageLine]
    by_agent: list[UsageLine]


def _latest_terms(db: Session, program: AffiliateProgram) -> list[AffiliateProgramTerm]:
    terms = db.scalars(select(AffiliateProgramTerm).where(AffiliateProgramTerm.program_id == program.id)
                       .order_by(AffiliateProgramTerm.term, AffiliateProgramTerm.created_at.desc(), AffiliateProgramTerm.id.desc()))
    latest: dict[str, AffiliateProgramTerm] = {}
    for term in terms:
        latest.setdefault(term.term, term)
    return list(latest.values())


def _batch_response(db: Session, run: AIResearchRun) -> BatchResponse:
    spec = run.content_spec_json or {}
    request = spec.get('request', {})
    workflow = db.scalar(select(Workflow).where(Workflow.research_run_id == run.id))
    return BatchResponse(run_id=run.id, workflow_id=workflow.id if workflow else None, workflow_status=workflow.status if workflow else None,
                         content_types=request.get('content_types', []), count_per_type=request.get('count_per_type', 1), max_cost_usd=run.max_cost_usd,
                         affiliate_link_id=UUID(spec['affiliate_link_id']),
                         source_count=db.scalar(select(func.count()).select_from(AIResearchSource).where(AIResearchSource.research_run_id == run.id)) or 0,
                         item_count=db.scalar(select(func.count()).select_from(ContentItem).where(ContentItem.batch_run_id == run.id)) or 0,
                         created_at=run.created_at)


@router.get('/{campaign_id}/content-batches', response_model=list[BatchResponse])
def list_batches(campaign_id: UUID, db: Session = Depends(get_db)):
    _campaign(db, campaign_id)
    runs = db.scalars(select(AIResearchRun).where(AIResearchRun.campaign_id == campaign_id, AIResearchRun.kind == 'CONTENT')
                      .order_by(AIResearchRun.created_at.desc(), AIResearchRun.id).limit(100))
    return [_batch_response(db, run) for run in runs]


@router.post('/{campaign_id}/content-batches', response_model=BatchResponse, status_code=201)
def create_batch(campaign_id: UUID, body: BatchCreate, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Freeze the campaign data into a content batch and its workflow. Nothing runs here."""
    path, payload = f'/api/v1/campaigns/{campaign_id}/content-batches', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, BatchResponse):
        return existing
    campaign = _campaign(db, campaign_id, lock=True, editable=True)
    if campaign.status != 'ACTIVE':
        raise HTTPException(status_code=409, detail='Activate the campaign before creating content')
    link = db.scalar(select(AffiliateLink).where(AffiliateLink.id == body.affiliate_link_id, AffiliateLink.campaign_id == campaign_id))
    if link is None or link.status != 'ACTIVE':
        raise HTTPException(status_code=409, detail='An active affiliate link of this campaign is required')
    program = db.get(AffiliateProgram, link.program_id)
    committed = db.scalar(select(func.coalesce(func.sum(AIResearchRun.max_cost_usd), 0)).where(AIResearchRun.campaign_id == campaign_id, AIResearchRun.kind == 'CONTENT'))
    if Decimal(committed) + body.max_cost_usd > Decimal(campaign.max_cost_usd):
        raise HTTPException(status_code=409, detail='Batch cost limits would exceed the campaign AI cost limit')
    sources = list(db.scalars(select(CampaignSource).where(CampaignSource.campaign_id == campaign_id, CampaignSource.verification_status != 'REJECTED')
                              .order_by(CampaignSource.created_at, CampaignSource.id).limit(MAX_SOURCES + 1)))
    if not sources:
        raise HTTPException(status_code=409, detail='Add at least one campaign source before creating content')
    if len(sources) > MAX_SOURCES:
        raise HTTPException(status_code=409, detail=f'A content batch can use at most {MAX_SOURCES} sources')
    # Fails with 409 before anything is written if the content agent has no profile, price or prompt.
    profile, price, prompt = _stage_inputs(db, 'AI_CONTENT_DRAFT', datetime.now(UTC))
    opportunity = db.get(Opportunity, campaign.opportunity_id)
    run = AIResearchRun(kind='CONTENT', campaign_id=campaign.id, objective=f'Content batch for campaign "{campaign.name}"', category='CONTENT',
                        target_market=(opportunity.target_market if opportunity and opportunity.target_market else 'Vietnam'),
                        target_customers=campaign.target_audience, max_cost_usd=body.max_cost_usd, status='DRAFT', created_by=actor,
                        content_spec_json={'pending': True})
    db.add(run)
    db.flush()
    # Snapshot the evidence: the batch keeps its own copies, so later campaign edits never change it.
    copies: dict[UUID, UUID] = {}
    for source in sources:
        copy = AIResearchSource(research_run_id=run.id, source_name=source.source_name, source_url=source.source_url, excerpt=source.excerpt,
                                verification_status=source.verification_status, verified_by=source.verified_by, verified_at=source.verified_at,
                                verification_note=f'Campaign source {source.id}' + (f': {source.verification_note}' if source.verification_note else ''))
        db.add(copy)
        db.flush()
        copies[source.id] = copy.id
    status_of = {source.id: source.verification_status for source in sources}

    def evidence(source_id: UUID | None) -> tuple[str, str | None] | None:
        if source_id is None:
            return 'UNSOURCED', None
        if source_id not in status_of:
            return None  # rejected since: never sent
        return status_of[source_id], str(copies[source_id])
    terms = []
    for term in _latest_terms(db, program):
        found = evidence(term.source_id)
        if found:
            terms.append({'term': term.term, 'value_text': term.value_text, 'value_numeric': None if term.value_numeric is None else str(term.value_numeric),
                          'unit': term.unit, 'evidence_status': found[0], 'source_id': found[1]})
    product = db.get(CampaignProduct, link.product_id) if link.product_id else None
    product_input = None
    if product:
        price_evidence = evidence(product.price_source_id) if product.price_text else None
        product_input = {'name': product.name, 'merchant': product.merchant, 'price_text': product.price_text if price_evidence else None,
                         'price_evidence_status': price_evidence[0] if price_evidence else 'UNSOURCED', 'price_source_id': price_evidence[1] if price_evidence else None}
    request = ContentRequest.model_validate({'language': campaign.language, 'campaign_name': campaign.name, 'niche': campaign.niche, 'target_audience': campaign.target_audience,
                                             'goal': campaign.goal, 'network': program.network, 'program_name': program.name, 'product': product_input, 'terms': terms[:20],
                                             'content_types': body.content_types, 'count_per_type': body.count_per_type})
    # The model must never see the real link: refuse Owner text that contains it (or any web address).
    sent = [*(source.excerpt or '' for source in sources), json.dumps(request.model_dump(mode='json'), ensure_ascii=False)]
    if any(url and url in text for text in sent for url in (link.original_url, link.final_url)) or any(_WEB_ADDRESS.search(text.replace('{{AFFILIATE_LINK}}', '')) for text in sent):
        raise HTTPException(status_code=409, detail='Campaign text, terms or source excerpts contain a web address; remove links before creating content')
    run.content_spec_json = {'request': request.model_dump(mode='json', exclude={'evidence'}), 'affiliate_link_id': str(link.id),
                             'product_id': str(product.id) if product else None, 'program_id': str(program.id)}
    workflow = Workflow(research_run_id=run.id, opportunity_id=None, name=f'{campaign.name} — content batch', created_by=actor, version=2)
    db.add(workflow)
    db.flush()
    validate = WorkflowTask(workflow_id=workflow.id, name='Validate content batch', task_type='VALIDATE_RESEARCH_DRAFT', assigned_role='research',
                            input_json={}, max_retries=0, timeout_seconds=30)
    db.add(validate)
    db.flush()
    draft = WorkflowTask(workflow_id=workflow.id, name='Draft content', task_type='AI_CONTENT_DRAFT', assigned_role=AI_TASK_ROLES['AI_CONTENT_DRAFT'],
                         input_json={'ai_price_id': str(price.id), 'ai_prompt_version_id': str(prompt.id)}, max_retries=0, timeout_seconds=min(profile.timeout_seconds, 300))
    db.add(draft)
    db.flush()
    db.add(TaskDependency(workflow_id=workflow.id, task_id=draft.id, depends_on_task_id=validate.id))
    db.add_all([
        WorkflowEvent(workflow_id=workflow.id, event_type='CREATED', new_status='DRAFT', actor=actor, metadata_json={'research_run_id': str(run.id), 'campaign_id': str(campaign.id)}),
        WorkflowEvent(workflow_id=workflow.id, task_id=validate.id, event_type='TASK_CREATED', new_status='PENDING', actor=actor, metadata_json={'task_type': validate.task_type}),
        WorkflowEvent(workflow_id=workflow.id, task_id=draft.id, event_type='TASK_CREATED', new_status='PENDING', actor=actor, metadata_json={'task_type': draft.task_type}),
    ])
    _audit(db, actor, 'campaign.content_batch_created', 'ai_research_run', run.id, campaign_id=campaign.id, workflow_id=workflow.id, link_id=link.id,
           content_types=list(body.content_types), count_per_type=body.count_per_type, max_cost_usd=str(body.max_cost_usd), prompt_version_id=prompt.id, price_id=price.id)
    db.flush()
    return _save(db, actor, key, 'POST', path, payload, _batch_response(db, run), 201, response, BatchResponse)


def _content_response(db: Session, item: ContentItem, *, detail: bool = False) -> ContentResponse | ContentDetail:
    versions = list(db.scalars(select(ContentVersion).where(ContentVersion.content_id == item.id).order_by(ContentVersion.version_no)))
    current = next(version for version in versions if version.version_no == item.current_version_no)
    fields = {c: getattr(item, c) for c in ('id', 'campaign_id', 'batch_run_id', 'content_type', 'language', 'status', 'product_id', 'affiliate_link_id',
                                             'decided_by', 'decided_at', 'decision_note', 'created_at', 'updated_at')}
    fields['current_version'] = VersionResponse.model_validate(current)
    if detail:
        checks = db.scalars(select(ContentCheck).where(ContentCheck.version_id == current.id).order_by(ContentCheck.check_name))
        records = db.scalars(select(ContentPublishRecord).where(ContentPublishRecord.content_id == item.id).order_by(ContentPublishRecord.published_at, ContentPublishRecord.id))
        return ContentDetail(**fields, versions=[VersionResponse.model_validate(version) for version in versions],
                             checks=[CheckResponse.model_validate(check) for check in checks], publish_records=[PublishRecordResponse.model_validate(record) for record in records])
    return ContentResponse(**fields)


@router.get('/{campaign_id}/content', response_model=list[ContentResponse])
def list_content(campaign_id: UUID, status: str | None = None, db: Session = Depends(get_db)):
    _campaign(db, campaign_id)
    statement = select(ContentItem).where(ContentItem.campaign_id == campaign_id)
    if status:
        statement = statement.where(ContentItem.status == status)
    items = db.scalars(statement.order_by(ContentItem.created_at.desc(), ContentItem.item_index, ContentItem.id).limit(200))
    return [_content_response(db, item) for item in items]


@router.get('/{campaign_id}/content/{content_id}', response_model=ContentDetail)
def get_content(campaign_id: UUID, content_id: UUID, db: Session = Depends(get_db)):
    _campaign(db, campaign_id)
    item = db.scalar(select(ContentItem).where(ContentItem.id == content_id, ContentItem.campaign_id == campaign_id))
    if item is None:
        raise HTTPException(status_code=404, detail='Content not found')
    return _content_response(db, item, detail=True)


@router.get('/{campaign_id}/usage', response_model=CampaignUsage)
def campaign_usage(campaign_id: UUID, db: Session = Depends(get_db)):
    """AI cost of the campaign's content batches. Token-based cost is an estimate until reconciled."""
    campaign = _campaign(db, campaign_id)
    runs = {run.id: run for run in db.scalars(select(AIResearchRun).where(AIResearchRun.campaign_id == campaign_id, AIResearchRun.kind == 'CONTENT'))}
    rows = db.execute(select(AIInvocation, BudgetReservation).join(BudgetReservation, BudgetReservation.id == AIInvocation.reservation_id)
                      .where(AIInvocation.research_run_id.in_(list(runs) or [UUID(int=0)]))).all()
    zero = Decimal('0')

    def held(reservation: BudgetReservation) -> Decimal:
        return zero if reservation.status in {'SETTLED', 'RELEASED'} else Decimal(reservation.reserved_amount)

    def group(key_of) -> list[UsageLine]:
        lines: dict[str, UsageLine] = {}
        for invocation, reservation in rows:
            key = key_of(invocation)
            line = lines.setdefault(key, UsageLine(key=key, invocations=0, estimated_cost=zero, calculated_cost=zero, held_amount=zero))
            line.invocations += 1
            line.estimated_cost += Decimal(invocation.estimated_cost)
            line.calculated_cost += Decimal(invocation.calculated_cost or 0)
            line.held_amount += held(reservation)
        return sorted(lines.values(), key=lambda line: line.key)
    return CampaignUsage(max_cost_usd=campaign.max_cost_usd, batch_limits_total=sum((Decimal(run.max_cost_usd) for run in runs.values()), zero),
                         invocations=len(rows), calculated_cost=sum((Decimal(i.calculated_cost or 0) for i, _ in rows), zero),
                         held_amount=sum((held(r) for _, r in rows), zero), by_batch=group(lambda i: str(i.research_run_id)), by_agent=group(lambda i: i.agent_role))
