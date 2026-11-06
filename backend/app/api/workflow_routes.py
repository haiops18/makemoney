"""Owner-only workflow drafting; execution endpoints remain unavailable."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.opportunity_routes import _commit_or_conflict, _idempotent, _store_idempotency
from app.api.workflow_schemas import AutoRunRequest, AutoRunResponse, TaskCreate, TaskExecutionResponse, TaskQueueRequest, TaskResponse, WorkflowCreate, WorkflowEventResponse, WorkflowList, WorkflowResponse, WorkflowSubmit, WorkflowSubmission, WorkflowUpdate
from app.approvals.service import consume_action_authorization, evaluate_policy
from app.auth.dependencies import require_owner
from app.core.action_hash import action_hash, canonical_action
from app.db.models import ActionAuthorization, Agent, AIResearchRun, ApprovalRequest, AuditEvent, Opportunity, Policy, TaskDependency, TaskExecution, Workflow, WorkflowAutoRun, WorkflowEvent, WorkflowTask
from app.db.session import get_db
from app.orchestration import auto_run
from app.orchestration.gate import GateDenied, authorize_task, task_action
from app.orchestration.state import TASK_TRANSITIONS, WORKFLOW_TRANSITIONS, validate_dependencies, validate_transition
from app.ai_brain.execution import AI_TASK_ROLES, AIExecutionDenied, prepare_ai_action, queue_ai_execution

router = APIRouter(prefix='/api/v1/workflows', dependencies=[Depends(require_owner)], tags=['workflows'])


def get_workflow(db: Session, workflow_id: UUID, lock: bool = False) -> Workflow:
    query = select(Workflow).where(Workflow.id == workflow_id)
    if lock:
        query = query.with_for_update()
    workflow = db.scalar(query)
    if workflow is None:
        raise HTTPException(status_code=404, detail='Workflow not found')
    return workflow


def workflow_response(db: Session, workflow: Workflow) -> WorkflowResponse:
    response = WorkflowResponse.model_validate(workflow)
    response.task_count = db.scalar(select(func.count()).select_from(WorkflowTask).where(WorkflowTask.workflow_id == workflow.id)) or 0
    response.succeeded_tasks = db.scalar(select(func.count()).select_from(WorkflowTask).where(WorkflowTask.workflow_id == workflow.id, WorkflowTask.status == 'SUCCEEDED')) or 0
    response.last_execution = db.scalar(select(func.max(TaskExecution.started_at)).join(WorkflowTask, WorkflowTask.id == TaskExecution.task_id).where(WorkflowTask.workflow_id == workflow.id))
    return response


@router.get('', response_model=WorkflowList)
def list_workflows(limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0), status_filter: str | None = None,
                   search: str | None = Query(default=None, max_length=200), opportunity_id: UUID | None = None,
                   assigned_role: str | None = Query(default=None, max_length=100), created_from: datetime | None = None,
                   created_to: datetime | None = None, sort_by: str = 'created_at', sort_dir: str = 'desc', db: Session = Depends(get_db)) -> WorkflowList:
    statement = select(Workflow)
    if status_filter:
        if status_filter not in WORKFLOW_TRANSITIONS:
            raise HTTPException(status_code=422, detail='Invalid workflow status')
        statement = statement.where(Workflow.status == status_filter)
    if search:
        statement = statement.where(Workflow.name.ilike('%' + search.strip() + '%'))
    if opportunity_id:
        statement = statement.where(Workflow.opportunity_id == opportunity_id)
    if assigned_role:
        statement = statement.where(select(WorkflowTask.id).where(WorkflowTask.workflow_id == Workflow.id, WorkflowTask.assigned_role == assigned_role).exists())
    for value in (created_from, created_to):
        if value is not None and value.tzinfo is None:
            raise HTTPException(status_code=422, detail='Date filters must include a timezone')
    if created_from and created_to and created_from > created_to:
        raise HTTPException(status_code=422, detail='Invalid date range')
    if created_from:
        statement = statement.where(Workflow.created_at >= created_from)
    if created_to:
        statement = statement.where(Workflow.created_at <= created_to)
    columns = {'created_at': Workflow.created_at, 'updated_at': Workflow.updated_at, 'name': Workflow.name, 'status': Workflow.status}
    if sort_by not in columns or sort_dir not in {'asc', 'desc'}:
        raise HTTPException(status_code=422, detail='Invalid sort field or direction')
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    column = columns[sort_by]
    items = list(db.scalars(statement.order_by(column.asc() if sort_dir == 'asc' else column.desc(), Workflow.id).offset(offset).limit(limit)))
    return WorkflowList(items=[workflow_response(db, item) for item in items], total=total, limit=limit, offset=offset)


@router.get('/summary')
def workflow_summary(db: Session = Depends(get_db)) -> dict:
    from decimal import Decimal
    counts = dict(db.execute(select(Workflow.status, func.count()).group_by(Workflow.status)).all())
    total_tasks = db.scalar(select(func.count()).select_from(WorkflowTask)) or 0
    succeeded = db.scalar(select(func.count()).select_from(WorkflowTask).where(WorkflowTask.status == 'SUCCEEDED')) or 0
    terminal = db.scalar(select(func.count()).select_from(WorkflowTask).where(WorkflowTask.status.in_(['SUCCEEDED', 'FAILED', 'CANCELLED', 'SKIPPED']))) or 0
    return {'total': sum(counts.values()), 'counts': counts, 'total_tasks': total_tasks,
            'task_success_rate': str(Decimal(succeeded) * 100 / Decimal(terminal)) if terminal else None}


@router.get('/recent-executions', response_model=list[TaskExecutionResponse])
def recent_executions(limit: int = Query(default=10, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)) -> list[TaskExecutionResponse]:
    rows = db.execute(select(TaskExecution, WorkflowTask.workflow_id).join(WorkflowTask, WorkflowTask.id == TaskExecution.task_id).order_by(TaskExecution.started_at.desc(), TaskExecution.id).offset(offset).limit(limit))
    return [TaskExecutionResponse.model_validate(item).model_copy(update={'workflow_id': workflow_id, 'input_fields': sorted((item.input_snapshot_json or {}).keys())}) for item, workflow_id in rows]


@router.post('', response_model=WorkflowResponse, status_code=201)
def create_workflow(body: WorkflowCreate, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> WorkflowResponse:
    path = '/api/v1/workflows'
    payload = body.model_dump(mode='json')
    existing = _idempotent(db, actor, key, 'POST', path, payload, WorkflowResponse)
    if existing:
        return existing
    opportunity = db.get(Opportunity, body.opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail='Opportunity not found')
    if opportunity.status in {'DISQUALIFIED', 'ARCHIVED'}:
        raise HTTPException(status_code=409, detail='Opportunity is not eligible for a workflow')
    workflow = Workflow(**body.model_dump(), created_by=actor)
    db.add(workflow)
    db.flush()
    result = WorkflowResponse.model_validate(workflow)
    db.add(AuditEvent(actor=actor, action='workflow.created', entity_type='workflow', entity_id=workflow.id, detail={'opportunity_id': str(workflow.opportunity_id)}))
    db.add(WorkflowEvent(workflow_id=workflow.id, event_type='CREATED', new_status='DRAFT', actor=actor, metadata_json={}))
    _store_idempotency(db, actor, key, 'POST', path, payload, result, 201)
    return _commit_or_conflict(db, actor, key, 'POST', path, payload, WorkflowResponse, response) or result


@router.get('/{workflow_id}', response_model=WorkflowResponse)
def workflow_detail(workflow_id: UUID, db: Session = Depends(get_db)) -> WorkflowResponse:
    return workflow_response(db, get_workflow(db, workflow_id))


@router.patch('/{workflow_id}', response_model=WorkflowResponse)
def update_workflow(workflow_id: UUID, body: WorkflowUpdate, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> WorkflowResponse:
    path = f'/api/v1/workflows/{workflow_id}'
    payload = body.model_dump(mode='json', exclude_unset=True)
    if not payload or ('name' in payload and payload['name'] is None):
        raise HTTPException(status_code=422, detail='A valid change is required')
    existing = _idempotent(db, actor, key, 'PATCH', path, payload, WorkflowResponse)
    if existing:
        return existing
    workflow = get_workflow(db, workflow_id, lock=True)
    if workflow.status != 'DRAFT':
        raise HTTPException(status_code=409, detail='Only drafts can be edited')
    for name, value in payload.items():
        setattr(workflow, name, value)
    workflow.version += 1
    db.add(AuditEvent(actor=actor, action='workflow.updated', entity_type='workflow', entity_id=workflow.id, detail={'fields': sorted(payload)}))
    db.add(WorkflowEvent(workflow_id=workflow.id, event_type='UPDATED', actor=actor, metadata_json={'fields': sorted(payload)}))
    db.flush()
    result = WorkflowResponse.model_validate(workflow)
    _store_idempotency(db, actor, key, 'PATCH', path, payload, result, 200)
    return _commit_or_conflict(db, actor, key, 'PATCH', path, payload, WorkflowResponse, response) or result


@router.get('/{workflow_id}/events', response_model=list[WorkflowEventResponse])
def workflow_events(workflow_id: UUID, limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)) -> list[WorkflowEventResponse]:
    get_workflow(db, workflow_id)
    events = db.scalars(select(WorkflowEvent).where(WorkflowEvent.workflow_id == workflow_id).order_by(WorkflowEvent.created_at.desc(), WorkflowEvent.id).offset(offset).limit(limit))
    return [WorkflowEventResponse.model_validate(event) for event in events]


@router.get('/{workflow_id}/executions', response_model=list[TaskExecutionResponse])
def workflow_executions(workflow_id: UUID, limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)) -> list[TaskExecutionResponse]:
    get_workflow(db, workflow_id)
    executions = db.scalars(select(TaskExecution).join(WorkflowTask, WorkflowTask.id == TaskExecution.task_id).where(WorkflowTask.workflow_id == workflow_id).order_by(TaskExecution.started_at.desc(), TaskExecution.id).offset(offset).limit(limit))
    return [TaskExecutionResponse.model_validate(execution).model_copy(update={'workflow_id': workflow_id, 'input_fields': sorted((execution.input_snapshot_json or {}).keys())}) for execution in executions]


@router.get('/{workflow_id}/tasks', response_model=list[TaskResponse])
def list_tasks(workflow_id: UUID, limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)) -> list[TaskResponse]:
    get_workflow(db, workflow_id)
    tasks = list(db.scalars(select(WorkflowTask).where(WorkflowTask.workflow_id == workflow_id).order_by(WorkflowTask.created_at, WorkflowTask.id).offset(offset).limit(limit)))
    dependencies = list(db.scalars(select(TaskDependency).where(TaskDependency.task_id.in_([task.id for task in tasks]))))
    return [TaskResponse.model_validate(task).model_copy(update={'depends_on': [item.depends_on_task_id for item in dependencies if item.task_id == task.id]}) for task in tasks]


@router.post('/{workflow_id}/tasks', response_model=TaskResponse, status_code=201)
def create_task(workflow_id: UUID, body: TaskCreate, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> TaskResponse:
    path = f'/api/v1/workflows/{workflow_id}/tasks'
    payload = body.model_dump(mode='json', exclude={'ai_price_id', 'ai_prompt_version_id'} if body.task_type not in AI_TASK_ROLES else set())
    existing = _idempotent(db, actor, key, 'POST', path, payload, TaskResponse)
    if existing:
        return existing
    workflow = get_workflow(db, workflow_id, lock=True)
    if workflow.status != 'DRAFT':
        raise HTTPException(status_code=409, detail='Tasks may only be added to a draft workflow')
    if (workflow.research_run_id is not None) != (body.task_type == 'VALIDATE_RESEARCH_DRAFT' or body.task_type in AI_TASK_ROLES):
        raise HTTPException(status_code=422, detail='Handler is incompatible with this workflow root')
    if (db.scalar(select(func.count()).select_from(WorkflowTask).where(WorkflowTask.workflow_id == workflow_id)) or 0) >= 100:
        raise HTTPException(status_code=409, detail='A workflow may contain at most 100 tasks')
    if len(set(body.depends_on)) != len(body.depends_on):
        raise HTTPException(status_code=422, detail='Duplicate dependencies')
    role = db.scalar(select(Agent).where(Agent.role == body.assigned_role, Agent.enabled.is_(True)))
    if role is None:
        raise HTTPException(status_code=422, detail='Assigned role is unavailable')
    parents = list(db.scalars(select(WorkflowTask.id).where(WorkflowTask.workflow_id == workflow_id, WorkflowTask.id.in_(body.depends_on))))
    if len(parents) != len(body.depends_on):
        raise HTTPException(status_code=422, detail='Dependencies must belong to the same workflow')
    ai_input = {'ai_price_id': str(body.ai_price_id), 'ai_prompt_version_id': str(body.ai_prompt_version_id)} if body.task_type in AI_TASK_ROLES else {}
    task = WorkflowTask(workflow_id=workflow_id, input_json=ai_input, **body.model_dump(exclude={'depends_on', 'ai_price_id', 'ai_prompt_version_id'}))
    db.add(task)
    db.flush()
    for parent in body.depends_on:
        db.add(TaskDependency(workflow_id=workflow_id, task_id=task.id, depends_on_task_id=parent))
    workflow.version += 1
    result = TaskResponse.model_validate(task).model_copy(update={'depends_on': body.depends_on})
    db.add(AuditEvent(actor=actor, action='workflow.task_created', entity_type='workflow_task', entity_id=task.id, detail={'workflow_id': str(workflow_id)}))
    db.add(WorkflowEvent(workflow_id=workflow_id, task_id=task.id, event_type='TASK_CREATED', new_status='PENDING', actor=actor, metadata_json={}))
    _store_idempotency(db, actor, key, 'POST', path, payload, result, 201)
    return _commit_or_conflict(db, actor, key, 'POST', path, payload, TaskResponse, response) or result


@router.get('/{workflow_id}/tasks/{task_id}/approval-action')
def approval_action(workflow_id: UUID, task_id: UUID, policy_id: UUID, db: Session = Depends(get_db)) -> dict:
    """Prepare the exact action for the existing Approval Center; grants no rights."""
    try:
        task = db.get(WorkflowTask, task_id)
        planner = prepare_ai_action if task and task.task_type in AI_TASK_ROLES else task_action
        action, digest = planner(db, workflow_id, task_id, policy_id)
    except (GateDenied, AIExecutionDenied) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {'action': action, 'action_hash': digest}


@router.get('/{workflow_id}/auto-run-action')
def auto_run_action(workflow_id: UUID, ai_policy_id: UUID, internal_policy_id: UUID, db: Session = Depends(get_db)) -> dict:
    """Prepare the one plan approval that lets the worker run every task in order; grants no rights."""
    workflow = get_workflow(db, workflow_id)
    try:
        action, digest = auto_run.prepare(db, workflow, ai_policy_id, internal_policy_id)
    except GateDenied as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    payload = action['action_payload']
    return {'action': action, 'action_hash': digest, 'summary': {
        'task_count': len(payload['tasks']), 'ai_task_count': sum(1 for task in payload['tasks'] if task['task_type'] in AI_TASK_ROLES),
        'max_cost_usd': payload['max_cost_usd'], 'source_count': len(payload['sources']),
        'models': sorted({profile['model_id'] for profile in payload['profiles'].values()})}}


@router.get('/{workflow_id}/auto-run', response_model=AutoRunResponse | None)
def get_auto_run(workflow_id: UUID, db: Session = Depends(get_db)) -> WorkflowAutoRun | None:
    get_workflow(db, workflow_id)
    return db.scalar(select(WorkflowAutoRun).where(WorkflowAutoRun.workflow_id == workflow_id).order_by(WorkflowAutoRun.created_at.desc(), WorkflowAutoRun.id.desc()).limit(1))


@router.post('/{workflow_id}/auto-run', response_model=AutoRunResponse, status_code=201)
def start_auto_run(workflow_id: UUID, body: AutoRunRequest, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> AutoRunResponse:
    path, payload = f'/api/v1/workflows/{workflow_id}/auto-run', body.model_dump(mode='json')
    existing = _idempotent(db, actor, key, 'POST', path, payload, AutoRunResponse)
    if existing:
        return existing
    workflow = get_workflow(db, workflow_id, lock=True)
    try:
        run = auto_run.activate(db, workflow, body.ai_policy_id, body.internal_policy_id, body.approval_id, actor)
    except GateDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    result = AutoRunResponse.model_validate(run)
    _store_idempotency(db, actor, key, 'POST', path, payload, result, 201)
    return _commit_or_conflict(db, actor, key, 'POST', path, payload, AutoRunResponse, response) or result


@router.post('/{workflow_id}/auto-run/stop', response_model=AutoRunResponse)
def stop_auto_run(workflow_id: UUID, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> AutoRunResponse:
    """Stop queuing further tasks. A task already queued or running still finishes."""
    path, payload = f'/api/v1/workflows/{workflow_id}/auto-run/stop', {}
    existing = _idempotent(db, actor, key, 'POST', path, payload, AutoRunResponse)
    if existing:
        return existing
    get_workflow(db, workflow_id, lock=True)
    run = db.scalar(select(WorkflowAutoRun).where(WorkflowAutoRun.workflow_id == workflow_id, WorkflowAutoRun.status == 'ACTIVE').with_for_update())
    if run is None:
        raise HTTPException(status_code=409, detail='Auto-run is not active')
    auto_run.end(db, run, 'STOPPED', auto_run.OWNER_STOP_REASON, actor)
    db.flush()
    result = AutoRunResponse.model_validate(run)
    _store_idempotency(db, actor, key, 'POST', path, payload, result, 200)
    return _commit_or_conflict(db, actor, key, 'POST', path, payload, AutoRunResponse, response) or result


def workflow_action(db: Session, workflow: Workflow, policy: Policy) -> tuple[dict, str]:
    tasks = list(db.scalars(select(WorkflowTask).where(WorkflowTask.workflow_id == workflow.id).order_by(WorkflowTask.id)))
    if not tasks:
        raise HTTPException(status_code=409, detail='Workflow must contain tasks')
    dependencies = list(db.scalars(select(TaskDependency).where(TaskDependency.workflow_id == workflow.id)))
    graph = {task.id: [item.depends_on_task_id for item in dependencies if item.task_id == task.id] for task in tasks}
    try:
        validate_dependencies(graph)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    payload = {'workflow_id': str(workflow.id), 'opportunity_id': str(workflow.opportunity_id), 'workflow_version': workflow.version,
        'name': workflow.name, 'description': workflow.description,
        'tasks': [{'id': str(task.id), 'name': task.name, 'description': task.description, 'task_type': task.task_type,
                   'assigned_role': task.assigned_role, 'priority': task.priority, 'max_retries': task.max_retries,
                   'timeout_seconds': task.timeout_seconds, 'input': task.input_json,
                   'depends_on': sorted(str(dep) for dep in graph[task.id])} for task in tasks]}
    if workflow.research_run_id is not None:
        payload['research_run_id'] = str(workflow.research_run_id)
    action = canonical_action('INTERNAL_WORKFLOW', payload, 'workflow', workflow.id, policy.id, policy.version, 'ONCE')
    return payload, action_hash(action)


def require_eligible_root(db: Session, workflow: Workflow) -> None:
    if workflow.research_run_id is not None:
        research = db.scalar(select(AIResearchRun).where(AIResearchRun.id == workflow.research_run_id).with_for_update())
        if research is None or research.status != 'DRAFT':
            raise HTTPException(status_code=409, detail='Research draft is not eligible')
    else:
        opportunity = db.scalar(select(Opportunity).where(Opportunity.id == workflow.opportunity_id).with_for_update())
        if opportunity is None or opportunity.status in {'DISQUALIFIED', 'ARCHIVED'}:
            raise HTTPException(status_code=409, detail='Opportunity is not eligible')


def record_transition(db: Session, workflow: Workflow, target: str, actor: str) -> None:
    try:
        validate_transition(WORKFLOW_TRANSITIONS, workflow.status, target)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    previous = workflow.status
    workflow.status = target
    db.add(WorkflowEvent(workflow_id=workflow.id, event_type='STATUS_CHANGED', previous_status=previous, new_status=target, actor=actor, metadata_json={}))
    db.add(AuditEvent(actor=actor, action='workflow.transition', entity_type='workflow', entity_id=workflow.id, detail={'previous_status': previous, 'new_status': target}))


@router.post('/{workflow_id}/submit', response_model=WorkflowSubmission)
def submit_workflow(workflow_id: UUID, body: WorkflowSubmit, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> WorkflowSubmission:
    path = f'/api/v1/workflows/{workflow_id}/submit'
    request = body.model_dump(mode='json')
    existing = _idempotent(db, actor, key, 'POST', path, request, WorkflowSubmission)
    if existing:
        return existing
    workflow = get_workflow(db, workflow_id, lock=True)
    if workflow.status != 'DRAFT':
        raise HTTPException(status_code=409, detail='Only a draft can be submitted')
    require_eligible_root(db, workflow)
    policy = db.scalar(select(Policy).where(Policy.id == body.policy_id).with_for_update())
    allowed, reason = evaluate_policy(policy, 'INTERNAL_WORKFLOW')
    if not allowed or policy is None or policy.rules_json.get('external_execution') is not False:
        raise HTTPException(status_code=403, detail=reason if not allowed else 'External execution must be disabled')
    payload, digest = workflow_action(db, workflow, policy)
    approval = ApprovalRequest(policy_id=policy.id, policy_version=policy.version, action_type='INTERNAL_WORKFLOW', action_hash=digest, action_payload_json=payload, resource_type='workflow', resource_id=workflow.id, requested_by=actor, expires_at=body.expires_at)
    db.add(approval)
    db.flush()
    db.add(AuditEvent(actor=actor, action='approval.requested', entity_type='approval_request', entity_id=approval.id, detail={'action_hash': digest, 'action_type': 'INTERNAL_WORKFLOW'}))
    db.add(WorkflowEvent(workflow_id=workflow.id, event_type='APPROVAL_REQUESTED', actor=actor, metadata_json={'approval_id': str(approval.id), 'action_hash': digest, 'workflow_version': workflow.version}))
    record_transition(db, workflow, 'PENDING_APPROVAL', actor)
    db.flush()
    result = WorkflowSubmission(workflow=WorkflowResponse.model_validate(workflow), approval_id=approval.id, action_hash=digest)
    _store_idempotency(db, actor, key, 'POST', path, request, result, 200)
    return _commit_or_conflict(db, actor, key, 'POST', path, request, WorkflowSubmission, response) or result


@router.post('/{workflow_id}/start', response_model=WorkflowResponse)
def start_workflow(workflow_id: UUID, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> WorkflowResponse:
    path = f'/api/v1/workflows/{workflow_id}/start'
    request: dict = {}
    existing = _idempotent(db, actor, key, 'POST', path, request, WorkflowResponse)
    if existing:
        return existing
    workflow = get_workflow(db, workflow_id, lock=True)
    if workflow.status != 'PENDING_APPROVAL':
        raise HTTPException(status_code=409, detail='Workflow is not pending approval')
    event = db.scalar(select(WorkflowEvent).where(WorkflowEvent.workflow_id == workflow.id, WorkflowEvent.event_type == 'APPROVAL_REQUESTED', WorkflowEvent.metadata_json['workflow_version'].as_integer() == workflow.version).order_by(WorkflowEvent.created_at.desc(), WorkflowEvent.id.desc()))
    if not event or not event.metadata_json.get('approval_id'):
        raise HTTPException(status_code=403, detail='Approval request unavailable')
    approval = db.get(ApprovalRequest, UUID(event.metadata_json['approval_id']))
    policy = db.scalar(select(Policy).where(Policy.id == approval.policy_id).with_for_update()) if approval else None
    allowed, reason = evaluate_policy(policy, 'INTERNAL_WORKFLOW')
    if not allowed or policy is None or policy.rules_json.get('external_execution') is not False or approval is None:
        raise HTTPException(status_code=403, detail=reason)
    require_eligible_root(db, workflow)
    _, digest = workflow_action(db, workflow, policy)
    authorization = db.scalar(select(ActionAuthorization).where(ActionAuthorization.approval_id == approval.id))
    if authorization is None or not consume_action_authorization(db, authorization.id, digest, actor):
        raise HTTPException(status_code=403, detail='Approval missing, expired, consumed or no longer matches workflow')
    record_transition(db, workflow, 'APPROVED', actor)
    record_transition(db, workflow, 'QUEUED', actor)
    db.flush()
    result = WorkflowResponse.model_validate(workflow)
    _store_idempotency(db, actor, key, 'POST', path, request, result, 200)
    return _commit_or_conflict(db, actor, key, 'POST', path, request, WorkflowResponse, response) or result


def control_workflow(workflow_id: UUID, operation: str, response: Response, key: str, actor: str, db: Session) -> WorkflowResponse:
    path = f'/api/v1/workflows/{workflow_id}/{operation}'
    request: dict = {}
    existing = _idempotent(db, actor, key, 'POST', path, request, WorkflowResponse)
    if existing:
        return existing
    workflow = get_workflow(db, workflow_id, lock=True)
    target = {'pause': 'PAUSED', 'resume': 'QUEUED', 'cancel': 'CANCELLED', 'reopen': 'DRAFT'}[operation]
    if operation == 'reopen':
        if workflow.status != 'PENDING_APPROVAL':
            raise HTTPException(status_code=409, detail='Only a pending workflow can be reopened')
        # New version guarantees all previous workflow and task hashes are stale.
        workflow.version += 1
    record_transition(db, workflow, target, actor)
    if target == 'CANCELLED':
        from datetime import UTC, datetime
        workflow.cancelled_at = datetime.now(UTC)
        tasks = db.scalars(select(WorkflowTask).where(WorkflowTask.workflow_id == workflow.id).order_by(WorkflowTask.id).with_for_update())
        for task in tasks:
            if task.status in {'PENDING', 'BLOCKED', 'READY', 'RETRY_WAIT'}:
                previous = task.status
                task.status = 'CANCELLED'
                task.finished_at = workflow.cancelled_at
                db.add(WorkflowEvent(workflow_id=workflow.id, task_id=task.id, event_type='TASK_CANCELLED', previous_status=previous, new_status='CANCELLED', actor=actor, metadata_json={}))
                db.add(AuditEvent(actor=actor, action='workflow.task_cancelled', entity_type='workflow_task', entity_id=task.id, detail={'workflow_id': str(workflow.id)}))
            elif task.status == 'RUNNING':
                queued = db.scalar(select(TaskExecution).where(TaskExecution.task_id == task.id, TaskExecution.status == 'QUEUED').with_for_update())
                if queued is not None:
                    queued.status = 'CANCELLED'
                    queued.completed_at = workflow.cancelled_at
                    task.status = 'CANCELLED'
                    task.finished_at = workflow.cancelled_at
                    db.add(WorkflowEvent(workflow_id=workflow.id, task_id=task.id, event_type='TASK_CANCELLED', previous_status='RUNNING', new_status='CANCELLED', actor=actor, metadata_json={'execution_id': str(queued.id)}))
                    db.add(AuditEvent(actor=actor, action='workflow.task_cancelled', entity_type='workflow_task', entity_id=task.id, detail={'workflow_id': str(workflow.id), 'execution_id': str(queued.id)}))
        # A running handler must cooperatively observe workflow cancellation and
        # discard output; no worker exists yet, so do not falsely mark it stopped.
    db.flush()
    result = WorkflowResponse.model_validate(workflow)
    _store_idempotency(db, actor, key, 'POST', path, request, result, 200)
    return _commit_or_conflict(db, actor, key, 'POST', path, request, WorkflowResponse, response) or result


@router.post('/{workflow_id}/pause', response_model=WorkflowResponse)
def pause_workflow(workflow_id: UUID, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> WorkflowResponse:
    return control_workflow(workflow_id, 'pause', response, key, actor, db)


@router.post('/{workflow_id}/resume', response_model=WorkflowResponse)
def resume_workflow(workflow_id: UUID, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> WorkflowResponse:
    return control_workflow(workflow_id, 'resume', response, key, actor, db)


@router.post('/{workflow_id}/cancel', response_model=WorkflowResponse)
def cancel_workflow(workflow_id: UUID, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> WorkflowResponse:
    return control_workflow(workflow_id, 'cancel', response, key, actor, db)


@router.post('/{workflow_id}/reopen', response_model=WorkflowResponse)
def reopen_workflow(workflow_id: UUID, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> WorkflowResponse:
    return control_workflow(workflow_id, 'reopen', response, key, actor, db)


@router.post('/{workflow_id}/tasks/{task_id}/queue', response_model=TaskExecutionResponse, status_code=201)
def queue_task(workflow_id: UUID, task_id: UUID, body: TaskQueueRequest, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> TaskExecutionResponse:
    from app.approvals.service import is_expired

    path = f'/api/v1/workflows/{workflow_id}/tasks/{task_id}/queue'
    payload = body.model_dump(mode='json')
    existing = _idempotent(db, actor, key, 'POST', path, payload, TaskExecutionResponse)
    if existing:
        return existing
    workflow = get_workflow(db, workflow_id, lock=True)
    task = db.scalar(select(WorkflowTask).where(WorkflowTask.id == task_id, WorkflowTask.workflow_id == workflow_id).with_for_update())
    if task is None:
        raise HTTPException(status_code=404, detail='Task not found')
    if workflow.status != 'RUNNING':
        raise HTTPException(status_code=409, detail='Workflow is not running')
    if task.status == 'RETRY_WAIT':
        if task.next_retry_at is None or not is_expired(task.next_retry_at) or task.retry_count >= task.max_retries:
            raise HTTPException(status_code=409, detail='Retry is not available')
        validate_transition(TASK_TRANSITIONS, task.status, 'READY')
        task.status = 'READY'
        task.retry_count += 1
        task.next_retry_at = None
        db.add(WorkflowEvent(workflow_id=workflow.id, task_id=task.id, event_type='RETRY_READY', previous_status='RETRY_WAIT', new_status='READY', actor=actor, metadata_json={'retry_count': task.retry_count}))
        db.add(AuditEvent(actor=actor, action='workflow.task_retry', entity_type='workflow_task', entity_id=task.id, detail={'workflow_id': str(workflow.id), 'retry_count': task.retry_count}))
    authorization = db.scalar(select(ActionAuthorization).where(ActionAuthorization.approval_id == body.approval_id))
    if authorization is None:
        raise HTTPException(status_code=403, detail='Task approval authorization unavailable')
    if task.task_type in AI_TASK_ROLES:
        try:
            execution = queue_ai_execution(db, workflow_id, task_id, body.policy_id, authorization.id, actor, key)
        except AIExecutionDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        result = TaskExecutionResponse.model_validate(execution).model_copy(update={'workflow_id': workflow_id, 'input_fields': sorted(execution.input_snapshot_json)})
        _store_idempotency(db, actor, key, 'POST', path, payload, result, 201)
        return _commit_or_conflict(db, actor, key, 'POST', path, payload, TaskExecutionResponse, response) or result
    try:
        handler_input = authorize_task(db, workflow_id, task_id, body.policy_id, authorization.id, actor)
    except GateDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    attempt = (db.scalar(select(func.max(TaskExecution.attempt_number)).where(TaskExecution.task_id == task.id)) or 0) + 1
    execution = TaskExecution(task_id=task.id, attempt_number=attempt, status='QUEUED', idempotency_key=key,
                              policy_id=body.policy_id, authorization_id=authorization.id,
                              action_hash=authorization.action_hash, input_snapshot_json=handler_input)
    db.add(execution)
    validate_transition(TASK_TRANSITIONS, task.status, 'RUNNING')
    task.status = 'RUNNING'
    db.flush()
    db.add(WorkflowEvent(workflow_id=workflow.id, task_id=task.id, event_type='TASK_QUEUED', previous_status='READY', new_status='RUNNING', actor=actor, metadata_json={'execution_id': str(execution.id), 'attempt': attempt}))
    db.add(AuditEvent(actor=actor, action='workflow.task_queued', entity_type='workflow_task', entity_id=task.id, detail={'workflow_id': str(workflow.id), 'execution_id': str(execution.id), 'attempt': attempt}))
    result = TaskExecutionResponse.model_validate(execution).model_copy(update={'workflow_id': workflow_id, 'input_fields': sorted(handler_input.keys())})
    _store_idempotency(db, actor, key, 'POST', path, payload, result, 201)
    return _commit_or_conflict(db, actor, key, 'POST', path, payload, TaskExecutionResponse, response) or result
