"""Step 7B discovery: the Owner asks the app to find ways to earn money in a field.

POST /discovery runs a bounded set of web searches through the Owner's search integration
(the Owner's click is the approval for those paid queries), stores every result as an
UNVERIFIED source and creates a research workflow: the seven existing stages plus an
opportunity-ranking stage. No model runs here; the Owner approves the AI run once with the
existing auto-run. Ranked candidates are proposals; only an Owner approval turns one into an
evaluated opportunity.
"""
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_brain.execution import AI_TASK_ROLES
from app.ai_brain.ranking_contract import SCORE_KEYS
from app.api.ai_research_routes import AI_DISCLAIMER, PIPELINE, _stage_inputs
from app.api.campaign_routes import IdempotencyKey, _audit, _save
from app.api.integration_routes import active_secret
from app.api.opportunity_routes import _idempotent
from app.api.opportunity_schemas import OpportunityEvaluate
from app.auth.dependencies import require_owner
from app.db.models import (Agent, AIInvocation, AIResearchRun, AIResearchSource, DiscoveryCandidate, Integration, Opportunity, OpportunityEvaluation,
                           OpportunityEvidence, OpportunityScoreDetail, TaskDependency, Workflow, WorkflowEvent, WorkflowTask)
from app.db.session import get_db
from app.integrations import search as search_module
from app.opportunities.service import calculate_score

router = APIRouter(prefix='/api/v1/discovery', dependencies=[Depends(require_owner)], tags=['discovery'])
RANKING = ('AI_OPPORTUNITY_RANKING', 'Opportunity ranking', ['AI_RESEARCH_REPORT'])
MAX_SOURCES = 20
QUERY_TEMPLATES = ('{topic} kiếm tiền online Việt Nam', '{topic} tiếp thị liên kết hoa hồng', '{topic} nhu cầu xu hướng thị trường Việt Nam',
                   'cách kiếm tiền từ {topic} cho người mới', '{topic} đối thủ cạnh tranh giá bán', '{topic} rủi ro quy định chính sách')
Query = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
# Replaced in tests; each call is one paid query with no retry.
search_transport = None


class DiscoveryCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    topic: str = Field(min_length=2, max_length=150)
    target_market: str = Field(default='Việt Nam', min_length=2, max_length=200)
    target_customers: str | None = Field(default=None, max_length=500)
    budget_note: str | None = Field(default=None, max_length=500)
    max_cost_usd: Decimal = Field(default=Decimal('2'), gt=0, le=10, decimal_places=6)
    query_count: int = Field(default=4, ge=1, le=6)
    results_per_query: int = Field(default=4, ge=1, le=5)
    queries: list[Query] | None = Field(default=None, min_length=1, max_length=6)
    search_kind: Literal['SEARCH_TAVILY', 'SEARCH_BRAVE'] | None = None


class SourceOut(BaseModel):
    id: UUID
    source_name: str
    source_url: str | None
    excerpt: str
    verification_status: str


class CandidateOut(BaseModel):
    id: UUID
    title: str
    business_model: str
    status: str
    rank_value: int
    data: dict[str, Any]
    decided_by: str | None
    decision_note: str | None
    opportunity_id: UUID | None


class DiscoverySummary(BaseModel):
    run_id: UUID
    topic: str
    target_market: str | None
    max_cost_usd: str
    workflow_id: UUID | None
    workflow_status: str | None
    source_count: int
    candidate_count: int
    created_at: datetime


class DiscoveryDetail(DiscoverySummary):
    queries: list[str]
    ranking_summary: str | None
    sources: list[SourceOut]
    candidates: list[CandidateOut]


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    note: str = Field(min_length=1, max_length=1000)


def _candidate_out(item: DiscoveryCandidate) -> CandidateOut:
    return CandidateOut(id=item.id, title=item.title, business_model=item.business_model, status=item.status, rank_value=item.rank_value, data=item.data_json,
                        decided_by=item.decided_by, decision_note=item.decision_note, opportunity_id=item.opportunity_id)


def _queries(run: AIResearchRun) -> list[str]:
    marker = '\nTruy vấn đã tìm: '
    return run.objective.split(marker, 1)[1].split(' | ') if marker in run.objective else []


def _summary(db: Session, run: AIResearchRun) -> DiscoverySummary:
    workflow = db.scalar(select(Workflow).where(Workflow.research_run_id == run.id))
    sources = db.scalar(select(func.count()).select_from(AIResearchSource).where(AIResearchSource.research_run_id == run.id)) or 0
    candidates = db.scalar(select(func.count()).select_from(DiscoveryCandidate).where(DiscoveryCandidate.run_id == run.id)) or 0
    return DiscoverySummary(run_id=run.id, topic=run.category or '', target_market=run.target_market, max_cost_usd=str(run.max_cost_usd), workflow_id=workflow.id if workflow else None,
                            workflow_status=workflow.status if workflow else None, source_count=sources, candidate_count=candidates, created_at=run.created_at)


def _detail(db: Session, run: AIResearchRun) -> DiscoveryDetail:
    sources = db.scalars(select(AIResearchSource).where(AIResearchSource.research_run_id == run.id).order_by(AIResearchSource.created_at, AIResearchSource.id))
    candidates = list(db.scalars(select(DiscoveryCandidate).where(DiscoveryCandidate.run_id == run.id)
                                 .order_by(DiscoveryCandidate.rank_value.desc(), DiscoveryCandidate.item_index)))
    summary = None
    if candidates:
        invocation = db.get(AIInvocation, candidates[0].source_invocation_id)
        summary = invocation.output_json.get('summary') if invocation and isinstance(invocation.output_json, dict) else None
    return DiscoveryDetail(**_summary(db, run).model_dump(), queries=_queries(run), ranking_summary=summary,
                           sources=[SourceOut(id=s.id, source_name=s.source_name, source_url=s.source_url, excerpt=s.excerpt, verification_status=s.verification_status) for s in sources],
                           candidates=[_candidate_out(item) for item in candidates])


def _run(db: Session, run_id: UUID, lock: bool = False) -> AIResearchRun:
    statement = select(AIResearchRun).where(AIResearchRun.id == run_id, AIResearchRun.kind == 'DISCOVERY')
    run = db.scalar(statement.with_for_update() if lock else statement)
    if run is None:
        raise HTTPException(status_code=404, detail='Discovery not found')
    return run


def _search_secret(db: Session, kind: str | None) -> tuple[Integration, str]:
    if kind:
        return active_secret(db, kind)
    for candidate in ('SEARCH_TAVILY', 'SEARCH_BRAVE'):
        exists = db.scalar(select(Integration.id).where(Integration.kind == candidate, Integration.archived.is_(False), Integration.enabled.is_(True)))
        if exists:
            return active_secret(db, candidate)
    raise HTTPException(status_code=409, detail='Connect a web search source (Tavily or Brave) on the Integrations page first')


def _add_workflow(db: Session, run: AIResearchRun, actor: str, now: datetime) -> Workflow:
    """Validation task, the seven research stages and the ranking stage; nothing is queued."""
    stages = [*PIPELINE, RANKING]
    inputs = {task_type: _stage_inputs(db, task_type, now) for task_type, _, _ in stages}  # 409 before anything is stored
    role = db.scalar(select(Agent).where(Agent.role == 'research', Agent.enabled.is_(True)))
    if role is None:
        raise HTTPException(status_code=409, detail='Research role is unavailable')
    workflow = Workflow(research_run_id=run.id, opportunity_id=None, name=f'Discovery: {run.category}'[:200], created_by=actor, version=2)
    db.add(workflow)
    db.flush()
    validate = WorkflowTask(workflow_id=workflow.id, name='Validate discovery sources', task_type='VALIDATE_RESEARCH_DRAFT', assigned_role=role.role,
                            input_json={}, max_retries=0, timeout_seconds=30)
    db.add(validate)
    db.flush()
    db.add(WorkflowEvent(workflow_id=workflow.id, event_type='CREATED', new_status='DRAFT', actor=actor, metadata_json={'research_run_id': str(run.id), 'kind': 'DISCOVERY'}))
    created: dict[str, WorkflowTask] = {}
    for task_type, name, parents in stages:
        profile, price, prompt = inputs[task_type]
        task = WorkflowTask(workflow_id=workflow.id, name=name, task_type=task_type, assigned_role=AI_TASK_ROLES[task_type],
                            input_json={'ai_price_id': str(price.id), 'ai_prompt_version_id': str(prompt.id)}, max_retries=0, timeout_seconds=min(profile.timeout_seconds, 300))
        db.add(task)
        db.flush()
        for dependency in ([created[parent].id for parent in parents] if parents else [validate.id]):
            db.add(TaskDependency(workflow_id=workflow.id, task_id=task.id, depends_on_task_id=dependency))
        created[task_type] = task
        db.add(WorkflowEvent(workflow_id=workflow.id, task_id=task.id, event_type='TASK_CREATED', new_status='PENDING', actor=actor, metadata_json={'task_type': task_type}))
    db.flush()
    _audit(db, actor, 'workflow.created', 'workflow', workflow.id, research_run_id=run.id, kind='DISCOVERY', task_count=len(stages) + 1)
    return workflow


@router.get('', response_model=list[DiscoverySummary])
def list_discoveries(db: Session = Depends(get_db)):
    runs = db.scalars(select(AIResearchRun).where(AIResearchRun.kind == 'DISCOVERY').order_by(AIResearchRun.created_at.desc(), AIResearchRun.id).limit(50))
    return [_summary(db, run) for run in runs]


@router.get('/{run_id}', response_model=DiscoveryDetail)
def get_discovery(run_id: UUID, db: Session = Depends(get_db)):
    return _detail(db, _run(db, run_id))


@router.post('', response_model=DiscoveryDetail, status_code=201)
def create_discovery(body: DiscoveryCreate, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path, payload = '/api/v1/discovery', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, DiscoveryDetail):
        return existing
    integration, secret = _search_secret(db, body.search_kind)
    now = datetime.now(UTC)
    for task_type, _, _ in [*PIPELINE, RANKING]:
        _stage_inputs(db, task_type, now)  # fail before any paid query
    queries = list(dict.fromkeys(body.queries or [template.format(topic=body.topic) for template in QUERY_TEMPLATES[:body.query_count]]))
    kind = integration.kind
    db.rollback()  # never hold a transaction while waiting on the network
    hits, failures = [], []
    try:
        for query in queries:
            try:
                kwargs = {'transport': search_transport} if search_transport else {}
                hits.extend(search_module.search(kind, secret, query, body.results_per_query, **kwargs))
            except search_module.SearchFailed as error:
                failures.append(str(error))
                if 'rejected' in str(error):
                    break
            except Exception:
                failures.append('The search service could not be reached')
    finally:
        secret = None
    if existing := _idempotent(db, actor, key, 'POST', path, payload, DiscoveryDetail):
        return existing
    unique = list({hit.url: hit for hit in hits}.values())[:MAX_SOURCES]
    if not unique:
        _audit(db, actor, 'discovery.search_failed', 'integration', integration.id, query_count=len(queries), reasons=sorted(set(failures))[:3])
        db.commit()
        raise HTTPException(status_code=502 if failures else 409, detail=(failures[0] if failures else 'The search found no usable results; try another topic'))
    objective = (f'Tìm các cách kiếm tiền khả thi cho một người ở {body.target_market} trong lĩnh vực: {body.topic}.'
                 + (f' Ngân sách và điều kiện: {body.budget_note}.' if body.budget_note else '')
                 + ' Nguồn là kết quả tìm kiếm web tự động, chưa được xác minh.'
                 + '\nTruy vấn đã tìm: ' + ' | '.join(queries))
    run = AIResearchRun(kind='DISCOVERY', objective=objective[:4000], category=body.topic, target_market=body.target_market, target_customers=body.target_customers,
                        max_cost_usd=body.max_cost_usd, status='DRAFT', created_by=actor)
    db.add(run)
    db.flush()
    for hit in unique:
        db.add(AIResearchSource(research_run_id=run.id, source_name=hit.title, source_url=hit.url, excerpt=hit.snippet, verification_status='UNVERIFIED'))
    db.flush()
    _add_workflow(db, run, actor, now)
    _audit(db, actor, 'discovery.created', 'ai_research_run', run.id, integration_id=integration.id, search_kind=kind, query_count=len(queries),
           source_count=len(unique), failed_queries=len(failures))
    return _save(db, actor, key, 'POST', path, payload, _detail(db, run), 201, response, DiscoveryDetail)


def _candidate(db: Session, run_id: UUID, candidate_id: UUID) -> DiscoveryCandidate:
    item = db.scalar(select(DiscoveryCandidate).where(DiscoveryCandidate.id == candidate_id, DiscoveryCandidate.run_id == run_id).with_for_update())
    if item is None:
        raise HTTPException(status_code=404, detail='Candidate not found')
    if item.status != 'PROPOSED':
        raise HTTPException(status_code=409, detail='This candidate has already been decided')
    return item


def _vnd(value: int) -> str:
    return f'{value:,}'.replace(',', '.') + 'đ'


@router.post('/{run_id}/candidates/{candidate_id}/approve', response_model=CandidateOut)
def approve_candidate(run_id: UUID, candidate_id: UUID, body: Decision, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """The Owner's decision: create the opportunity with the AI estimates as its evaluation."""
    path, payload = f'/api/v1/discovery/{run_id}/candidates/{candidate_id}/approve', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, CandidateOut):
        return existing
    run = _run(db, run_id, lock=True)
    item = _candidate(db, run_id, candidate_id)
    data = item.data_json
    description = '\n'.join([AI_DISCLAIMER, '', data['summary'], '',
                             f"Thu nhập ước tính/tháng: {_vnd(data['income_low_vnd'])} – {_vnd(data['income_high_vnd'])} (cơ sở {_vnd(data['income_base_vnd'])}); "
                             f"khả năng đạt: {data['success_likelihood']}%; vốn ban đầu {_vnd(data['startup_cost_vnd'])}; chi phí/tháng {_vnd(data['monthly_cost_vnd'])}; "
                             f"thu nhập đầu tiên sau ~{data['weeks_to_first_income']} tuần; {data['hours_per_week']} giờ/tuần.",
                             'Cách làm: ' + ' → '.join(data['how_it_works']), 'Giả định: ' + '; '.join(data['assumptions'])])[:5000]
    opportunity = Opportunity(title=item.title, description=description, category=(run.category or '')[:100] or None, target_market=run.target_market,
                              target_customer=run.target_customers, business_model=item.business_model, monetization_method=None, status='DRAFT',
                              data_origin='AI_DISCOVERY', created_by=actor)
    db.add(opportunity)
    db.flush()
    cited = {str(source_id) for source_id in data.get('source_ids', [])}
    sources = db.scalars(select(AIResearchSource).where(AIResearchSource.research_run_id == run.id, AIResearchSource.verification_status != 'REJECTED')
                         .order_by(AIResearchSource.created_at, AIResearchSource.id))
    for source in sources:
        if cited and str(source.id) not in cited:
            continue
        db.add(OpportunityEvidence(opportunity_id=opportunity.id, source_url=source.source_url, source_name=source.source_name, source_type='WEB_SEARCH_RESULT',
                                   evidence_type=f'DISCOVERY_SOURCE:{source.id}', summary=source.excerpt[:5000], captured_at=source.created_at,
                                   verification_status=source.verification_status))
    evaluation = OpportunityEvaluate(scores={name: data['scores'][name] for name in SCORE_KEYS}, risk_level=data['risk_level'],
                                     risk_assessment='; '.join(data['risks'])[:1000])
    weighted, total, disqualified, reason, recommendation = calculate_score(evaluation)
    db.add(OpportunityScoreDetail(opportunity_id=opportunity.id, scoring_version=evaluation.scoring_version, market_demand_score=weighted['market_demand'],
                                  monetization_score=weighted['monetization_potential'], automation_score=weighted['automation_feasibility'],
                                  cost_efficiency_score=weighted['experiment_cost'], competitive_advantage_score=weighted['competitive_advantage'],
                                  scalability_score=weighted['scalability'], evidence_confidence_score=weighted['evidence_confidence'], total_score=total,
                                  disqualified=disqualified, disqualification_reason=reason))
    opportunity.score, opportunity.confidence_score, opportunity.risk_level = int(total), evaluation.scores.evidence_confidence, evaluation.risk_level
    opportunity.status = 'DISQUALIFIED' if disqualified else 'EVALUATED'
    now = datetime.now(UTC)
    db.add(OpportunityEvaluation(opportunity_id=opportunity.id, scoring_version=evaluation.scoring_version, input_snapshot_json=evaluation.model_dump(mode='json') | {'origin': 'AI_DISCOVERY'},
                                 result_snapshot_json={'total_score': str(total), 'recommendation': recommendation, 'disqualified': disqualified, 'disqualification_reason': reason,
                                                       'breakdown': {name: str(value) for name, value in weighted.items()}}, evaluated_by=actor, evaluated_at=now))
    item.status, item.decided_by, item.decided_at, item.decision_note, item.opportunity_id = 'APPROVED', actor, now, body.note, opportunity.id
    db.flush()
    _audit(db, actor, 'discovery.candidate_approved', 'discovery_candidate', item.id, run_id=run.id, opportunity_id=opportunity.id, total_score=str(total))
    _audit(db, actor, 'opportunity.created', 'opportunity', opportunity.id, business_model=opportunity.business_model, data_origin='AI_DISCOVERY')
    _audit(db, actor, 'opportunity.evaluated', 'opportunity', opportunity.id, scoring_version=evaluation.scoring_version, disqualified=disqualified, total_score=str(total))
    return _save(db, actor, key, 'POST', path, payload, _candidate_out(item), 200, response, CandidateOut)


@router.post('/{run_id}/candidates/{candidate_id}/reject', response_model=CandidateOut)
def reject_candidate(run_id: UUID, candidate_id: UUID, body: Decision, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path, payload = f'/api/v1/discovery/{run_id}/candidates/{candidate_id}/reject', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, CandidateOut):
        return existing
    _run(db, run_id, lock=True)
    item = _candidate(db, run_id, candidate_id)
    item.status, item.decided_by, item.decided_at, item.decision_note = 'REJECTED', actor, datetime.now(UTC), body.note
    db.flush()
    _audit(db, actor, 'discovery.candidate_rejected', 'discovery_candidate', item.id, run_id=run_id)
    return _save(db, actor, key, 'POST', path, payload, _candidate_out(item), 200, response, CandidateOut)
