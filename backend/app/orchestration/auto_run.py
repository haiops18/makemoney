"""Workflow auto-run: one Owner approval queues every task of a research workflow in order.

The Owner approves a server-derived *plan* (tasks and dependencies, pinned prompts and
prices, agent profiles and credentials, sources, policies and the research cost limit).
The worker then queues each READY task in dependency order without a per-task approval.

Controls are not relaxed per call: every queue, claim and dispatch recomputes the plan
and requires it to match the approved hash, and every AI call still needs global
consent, an AI policy, a run cost-limit check and its own budget reservation. Any
change, denial, failure, pause, cancellation or expiry stops the auto-run; it never
retries a paid call and never resumes by itself.
"""
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.approvals.service import consume_action_authorization, evaluate_policy, is_expired
from app.core.action_hash import action_hash, canonical_action
from app.db.models import (ActionAuthorization, Agent, AIAgentProfile, AIExecutionControl, AIProvider, AIResearchRun, AIResearchSource,
                           AuditEvent, Policy, TaskDependency, TaskExecution, Workflow, WorkflowAutoRun, WorkflowEvent, WorkflowTask)
from app.orchestration.gate import GateDenied, runnable_task_action
from app.orchestration.state import TASK_TRANSITIONS, validate_transition

AUTO_RUN_TTL = timedelta(hours=12)
AUTO_RUN_ACTOR = 'auto-run'
INTERNAL_TASKS = {'VALIDATE_RESEARCH_DRAFT'}
# Approval may precede start; tasks are only queued while the workflow is RUNNING.
PLAN_STATUSES = {'DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'QUEUED', 'RUNNING', 'PAUSED'}


class AutoRunDenied(GateDenied):
    """The auto-run plan could not be verified; nothing may be queued under it."""


def _ai_roles() -> dict[str, str]:
    from app.ai_brain.execution import AI_TASK_ROLES
    return AI_TASK_ROLES


def plan_action(db: Session, workflow: Workflow, ai_policy_id: UUID, internal_policy_id: UUID) -> tuple[dict, str]:
    """Server-derived auto-run plan. Excludes task statuses so it stays stable while tasks run."""
    roles = _ai_roles()
    if workflow.research_run_id is None:
        raise AutoRunDenied('Auto-run is available for research workflows only')
    control = db.scalar(select(AIExecutionControl).where(AIExecutionControl.name == 'primary').with_for_update())
    if control is None or not control.enabled:
        raise AutoRunDenied('Global AI consent is disabled')
    ai_policy = db.scalar(select(Policy).where(Policy.id == ai_policy_id).with_for_update())
    allowed, _ = evaluate_policy(ai_policy, 'AI_INFERENCE')
    if not allowed or ai_policy is None or ai_policy.rules_json.get('external_execution') is not False or ai_policy.rules_json.get('ai_inference_allowed') is not True:
        raise AutoRunDenied('Policy denies AI inference')
    internal = db.scalar(select(Policy).where(Policy.id == internal_policy_id).with_for_update())
    allowed, _ = evaluate_policy(internal, 'INTERNAL_WORKFLOW')
    if not allowed or internal is None or internal.rules_json.get('external_execution') is not False:
        raise AutoRunDenied('Policy denies internal workflow tasks')
    research = db.scalar(select(AIResearchRun).where(AIResearchRun.id == workflow.research_run_id).with_for_update())
    if research is None or research.status != 'DRAFT':
        raise AutoRunDenied('Research draft is unavailable')
    sources = list(db.scalars(select(AIResearchSource).where(AIResearchSource.research_run_id == research.id).order_by(AIResearchSource.id)))
    if not sources:
        raise AutoRunDenied('Add at least one research source before auto-run')
    tasks = list(db.scalars(select(WorkflowTask).where(WorkflowTask.workflow_id == workflow.id).order_by(WorkflowTask.created_at, WorkflowTask.id)))
    if not any(task.task_type in roles for task in tasks):
        raise AutoRunDenied('Add the AI stages before auto-run')
    dependencies = list(db.scalars(select(TaskDependency).where(TaskDependency.workflow_id == workflow.id)))
    planned, profiles = [], {}
    for task in tasks:
        if task.task_type not in roles and task.task_type not in INTERNAL_TASKS:
            raise AutoRunDenied('Workflow contains a task that auto-run does not allow')
        entry = {'task_id': str(task.id), 'task_type': task.task_type, 'assigned_role': task.assigned_role, 'max_retries': task.max_retries,
                 'depends_on': sorted(str(dep.depends_on_task_id) for dep in dependencies if dep.task_id == task.id)}
        if task.task_type in roles:
            if task.max_retries != 0 or task.assigned_role != roles[task.task_type]:
                raise AutoRunDenied('AI task configuration is not allowed for auto-run')
            entry['price_id'] = str((task.input_json or {}).get('ai_price_id'))
            entry['prompt_version_id'] = str((task.input_json or {}).get('ai_prompt_version_id'))
            if task.assigned_role not in profiles:
                profiles[task.assigned_role] = _profile_entry(db, task.assigned_role)
        planned.append(entry)
    payload = {'mode': 'WORKFLOW_AUTO_RUN', 'workflow_id': str(workflow.id), 'workflow_version': workflow.version,
               'research_run_id': str(research.id), 'max_cost_usd': str(research.max_cost_usd), 'control_version': control.version,
               'internal_policy_id': str(internal.id), 'internal_policy_version': internal.version,
               'tasks': planned, 'profiles': profiles,
               'sources': [{'source_id': str(source.id), 'verification_status': source.verification_status} for source in sources]}
    action = canonical_action('AI_INFERENCE', payload, 'workflow', workflow.id, ai_policy.id, ai_policy.version, 'ONCE')
    return action, action_hash(action)


def _profile_entry(db: Session, role: str) -> dict:
    agent = db.scalar(select(Agent).where(Agent.role == role, Agent.enabled.is_(True)))
    profile = db.scalar(select(AIAgentProfile).where(AIAgentProfile.agent_id == agent.id)) if agent else None
    provider = db.get(AIProvider, profile.provider_id) if profile else None
    if profile is None or not profile.enabled or provider is None or not provider.enabled or provider.archived or not provider.encrypted_api_key:
        raise AutoRunDenied(f'The {role} agent AI profile or provider is unavailable')
    return {'profile_id': str(profile.id), 'provider_id': str(provider.id), 'provider_kind': provider.kind, 'model_id': profile.model_id,
            'credential_version': hashlib.sha256(provider.encrypted_api_key.encode()).hexdigest(),
            'max_output_tokens': profile.max_output_tokens, 'max_cost_usd': str(profile.max_cost_usd), 'timeout_seconds': profile.timeout_seconds}


def prepare(db: Session, workflow: Workflow, ai_policy_id: UUID, internal_policy_id: UUID) -> tuple[dict, str]:
    if workflow.status not in PLAN_STATUSES:
        raise AutoRunDenied('Workflow has already finished')
    tasks = list(db.scalars(select(WorkflowTask.status).where(WorkflowTask.workflow_id == workflow.id)))
    if any(status in {'FAILED', 'CANCELLED'} for status in tasks):
        raise AutoRunDenied('Workflow has a failed or cancelled task')
    if tasks and all(status == 'SUCCEEDED' for status in tasks):
        raise AutoRunDenied('Every task has already succeeded')
    return plan_action(db, workflow, ai_policy_id, internal_policy_id)


def activate(db: Session, workflow: Workflow, ai_policy_id: UUID, internal_policy_id: UUID, approval_id: UUID, actor: str) -> WorkflowAutoRun:
    """Consume the Owner's one approval of the current plan and start the auto-run."""
    if actor != 'owner':
        raise AutoRunDenied('Owner authorization is required')
    if db.scalar(select(WorkflowAutoRun.id).where(WorkflowAutoRun.workflow_id == workflow.id, WorkflowAutoRun.status == 'ACTIVE')):
        raise AutoRunDenied('Auto-run is already active for this workflow')
    _, digest = prepare(db, workflow, ai_policy_id, internal_policy_id)
    authorization = db.scalar(select(ActionAuthorization).where(ActionAuthorization.approval_id == approval_id))
    if authorization is None or not consume_action_authorization(db, authorization.id, digest, actor):
        raise AutoRunDenied('Approval is missing, expired, consumed or no longer matches the plan')
    run = WorkflowAutoRun(workflow_id=workflow.id, workflow_version=workflow.version, ai_policy_id=ai_policy_id, internal_policy_id=internal_policy_id,
                          approval_id=approval_id, authorization_id=authorization.id, plan_hash=digest, status='ACTIVE',
                          expires_at=datetime.now(UTC) + AUTO_RUN_TTL, created_by=actor)
    db.add(run)
    db.flush()
    db.add(WorkflowEvent(workflow_id=workflow.id, event_type='AUTO_RUN_STARTED', actor=actor, metadata_json={'auto_run_id': str(run.id), 'plan_hash': digest}))
    db.add(AuditEvent(actor=actor, action='workflow.auto_run_started', entity_type='workflow_auto_run', entity_id=run.id,
                      detail={'workflow_id': str(workflow.id), 'approval_id': str(approval_id), 'plan_hash': digest}))
    return run


def end(db: Session, run: WorkflowAutoRun, status: str, reason: str | None, actor: str) -> None:
    if run.status != 'ACTIVE':
        return
    run.status, run.stop_reason, run.ended_at = status, reason[:300] if reason else None, datetime.now(UTC)
    db.add(WorkflowEvent(workflow_id=run.workflow_id, event_type='AUTO_RUN_COMPLETED' if status == 'COMPLETED' else 'AUTO_RUN_STOPPED', actor=actor,
                         metadata_json={'auto_run_id': str(run.id), 'reason': run.stop_reason}))
    db.add(AuditEvent(actor=actor, action=f'workflow.auto_run_{status.lower()}', entity_type='workflow_auto_run', entity_id=run.id,
                      detail={'workflow_id': str(run.workflow_id), 'reason': run.stop_reason}))


OWNER_STOP_REASON = 'Stopped by Owner'


def verify_auto_run(db: Session, auto_run_id: UUID, workflow: Workflow, *, in_flight: bool = False) -> WorkflowAutoRun:
    """Fail closed unless the auto-run is ACTIVE, unexpired and its plan is unchanged.

    ``in_flight`` is for an execution queued while the auto-run was ACTIVE: an Owner
    stop only prevents further queuing, so that execution may still finish, but its
    plan must still match.
    """
    run = db.scalar(select(WorkflowAutoRun).where(WorkflowAutoRun.id == auto_run_id).with_for_update())
    usable = run is not None and (run.status == 'ACTIVE' or (in_flight and run.status == 'STOPPED' and run.stop_reason == OWNER_STOP_REASON))
    if not usable or is_expired(run.expires_at) or run.workflow_id != workflow.id or run.workflow_version != workflow.version:
        raise AutoRunDenied('Auto-run is not active')
    authorization = db.get(ActionAuthorization, run.authorization_id)
    if authorization is None or authorization.status != 'CONSUMED' or authorization.action_hash != run.plan_hash:
        raise AutoRunDenied('Auto-run approval is invalid')
    _, digest = plan_action(db, workflow, run.ai_policy_id, run.internal_policy_id)
    if digest != run.plan_hash:
        raise AutoRunDenied('Workflow, configuration or sources changed after the auto-run approval')
    return run


def _queue(db: Session, run: WorkflowAutoRun, workflow: Workflow, task: WorkflowTask) -> TaskExecution:
    attempt = (db.scalar(select(func.max(TaskExecution.attempt_number)).where(TaskExecution.task_id == task.id)) or 0) + 1
    key = f'auto-run:{run.id}:{task.id}:{attempt}'
    if task.task_type in _ai_roles():
        from app.ai_brain.execution import queue_ai_execution
        return queue_ai_execution(db, workflow.id, task.id, run.ai_policy_id, None, AUTO_RUN_ACTOR, key, auto_run_id=run.id)
    action, digest = runnable_task_action(db, workflow.id, task.id, run.internal_policy_id)
    handler_input = action['action_payload']['handler_input']
    execution = TaskExecution(task_id=task.id, attempt_number=attempt, status='QUEUED', idempotency_key=key, policy_id=run.internal_policy_id,
                              auto_run_id=run.id, action_hash=digest, input_snapshot_json=handler_input)
    db.add(execution)
    validate_transition(TASK_TRANSITIONS, task.status, 'RUNNING')
    task.status = 'RUNNING'
    db.flush()
    db.add(WorkflowEvent(workflow_id=workflow.id, task_id=task.id, event_type='TASK_QUEUED', previous_status='READY', new_status='RUNNING', actor=AUTO_RUN_ACTOR,
                         metadata_json={'execution_id': str(execution.id), 'attempt': attempt, 'auto_run_id': str(run.id)}))
    db.add(AuditEvent(actor=AUTO_RUN_ACTOR, action='workflow.task_queued', entity_type='workflow_task', entity_id=task.id,
                      detail={'workflow_id': str(workflow.id), 'execution_id': str(execution.id), 'attempt': attempt, 'auto_run_id': str(run.id)}))
    return execution


def auto_queue_one(factory: sessionmaker) -> bool:
    """Queue at most one READY task of one ACTIVE auto-run, or close a finished auto-run."""
    from app.ai_brain.execution import AIExecutionDenied

    with factory.begin() as db:
        ids = list(db.scalars(select(WorkflowAutoRun.id).where(WorkflowAutoRun.status == 'ACTIVE').order_by(WorkflowAutoRun.created_at, WorkflowAutoRun.id).limit(50)))
        for run_id in ids:
            workflow_id = db.scalar(select(WorkflowAutoRun.workflow_id).where(WorkflowAutoRun.id == run_id))
            workflow = db.scalar(select(Workflow).where(Workflow.id == workflow_id).with_for_update(skip_locked=True))
            run = db.scalar(select(WorkflowAutoRun).where(WorkflowAutoRun.id == run_id).with_for_update(skip_locked=True)) if workflow else None
            if workflow is None or run is None or run.status != 'ACTIVE':
                continue
            if workflow.status == 'COMPLETED':
                end(db, run, 'COMPLETED', None, AUTO_RUN_ACTOR)
                return True
            if workflow.status in {'FAILED', 'CANCELLED'}:
                end(db, run, 'STOPPED', f'Workflow {workflow.status.lower()}', AUTO_RUN_ACTOR)
                return True
            if is_expired(run.expires_at):
                end(db, run, 'STOPPED', 'Auto-run approval expired', AUTO_RUN_ACTOR)
                return True
            if workflow.status != 'RUNNING':
                continue  # Paused or queued: wait; never queue outside RUNNING.
            task = db.scalar(select(WorkflowTask).where(WorkflowTask.workflow_id == workflow.id, WorkflowTask.status == 'READY')
                             .order_by(WorkflowTask.created_at, WorkflowTask.id).with_for_update(skip_locked=True).limit(1))
            if task is None:
                continue
            try:
                with db.begin_nested():
                    verify_auto_run(db, run.id, workflow)
                    _queue(db, run, workflow, task)
            except (GateDenied, AIExecutionDenied) as exc:
                end(db, run, 'STOPPED', str(exc), AUTO_RUN_ACTOR)
            return True
    return False
