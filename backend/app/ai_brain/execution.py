"""Server-derived AI action plans and guarded, one-shot provider dispatch.

An action plan is not an authorization. Dispatch additionally needs an atomic
approval consumption, budget reservation, execution record and valid worker lease.
"""
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_brain.adapters import adapter_for
from app.ai_brain.openai_contract import ProviderOutputError
from app.ai_brain.accounting import record_outcome
from app.ai_brain.credentials import decrypt_credential
from app.ai_brain.network import post_provider_json
from app.ai_brain.pricing import Pricing
from app.ai_brain.content_contract import ContentRequest
from app.ai_brain.output_contracts import CONTENT_DRAFT, contract_for_prompt, contract_named
from app.ai_brain.prompts import EvidenceInput, PriorStageOutput, PromptTemplate, ResearchRequest
from app.approvals.service import consume_action_authorization, evaluate_policy
from app.approvals.service import is_expired
from app.core.action_hash import action_hash, canonical_action
from app.db.models import ActionAuthorization, Agent, AIAgentProfile, AIExecutionControl, AIInvocation, AIModelPrice, AIPromptVersion, AIProvider, AIResearchRun, AIResearchSource, ApprovalRequest, AuditEvent, BudgetAccount, BudgetReservation, Policy, TaskDependency, TaskExecution, Workflow, WorkflowEvent, WorkflowTask
from app.finance.service import committed_amount, create_reservation
from app.orchestration.state import TASK_TRANSITIONS, validate_transition

AI_TASK_ROLES = {'AI_RESEARCH_PLAN': 'research', 'AI_MARKET_RESEARCH': 'research', 'AI_COMPETITOR_ANALYSIS': 'research',
                 'AI_OPPORTUNITY_GENERATION': 'ceo', 'AI_FINANCIAL_ANALYSIS': 'finance', 'AI_RISK_REVIEW': 'auditor', 'AI_RESEARCH_REPORT': 'ceo',
                 'AI_CONTENT_DRAFT': 'content'}
# Each stage uses its own immutable prompt family; versions are pinned per task.
AI_TASK_PROMPTS = {'AI_RESEARCH_PLAN': 'research', 'AI_MARKET_RESEARCH': 'market_research', 'AI_COMPETITOR_ANALYSIS': 'competitor_analysis',
                   'AI_OPPORTUNITY_GENERATION': 'opportunity_generation', 'AI_FINANCIAL_ANALYSIS': 'financial_analysis',
                   'AI_RISK_REVIEW': 'risk_review', 'AI_RESEARCH_REPORT': 'research_report', 'AI_CONTENT_DRAFT': 'content_draft'}
# Step 7A content tasks run only on CONTENT runs; research tasks only on RESEARCH runs.
CONTENT_TASKS = {'AI_CONTENT_DRAFT'}
MAX_PRIOR_OUTPUTS = 10


class AIExecutionDenied(ValueError):
    pass


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _prior_outputs(db: Session, task: WorkflowTask) -> list[PriorStageOutput]:
    """Validated outputs of direct AI dependencies, ordered deterministically."""
    parents = list(db.scalars(select(WorkflowTask).join(TaskDependency, TaskDependency.depends_on_task_id == WorkflowTask.id)
                              .where(TaskDependency.task_id == task.id).order_by(WorkflowTask.created_at, WorkflowTask.id)))
    outputs = []
    for parent in parents:
        if parent.task_type not in AI_TASK_ROLES:
            continue
        if parent.status != 'SUCCEEDED':
            # Never send a stage with missing prior context; that would bill a degraded request.
            raise AIExecutionDenied('A prior AI stage has not succeeded')
        invocation = db.scalar(select(AIInvocation).join(TaskExecution, TaskExecution.id == AIInvocation.execution_id)
                               .where(TaskExecution.task_id == parent.id, TaskExecution.status == 'SUCCEEDED', AIInvocation.status == 'SUCCEEDED')
                               .order_by(TaskExecution.attempt_number.desc()).limit(1))
        if invocation is None or not isinstance(invocation.output_json, dict) or not isinstance(invocation.output_json.get('summary'), str):
            raise AIExecutionDenied('A prior AI stage output is unavailable')
        outputs.append(PriorStageOutput(stage=parent.task_type, summary=invocation.output_json['summary'], findings=invocation.output_json.get('findings', [])))
    if len(outputs) > MAX_PRIOR_OUTPUTS:
        raise AIExecutionDenied('AI task has too many prior stage outputs')
    return outputs


def prepare_ai_action(db: Session, workflow_id: UUID, task_id: UUID, policy_id: UUID) -> tuple[dict, str]:
    workflow = db.scalar(select(Workflow).where(Workflow.id == workflow_id).with_for_update())
    task = db.scalar(select(WorkflowTask).where(WorkflowTask.id == task_id, WorkflowTask.workflow_id == workflow_id).with_for_update())
    if workflow is None or task is None or not workflow.research_run_id or task.task_type not in AI_TASK_ROLES:
        raise AIExecutionDenied('AI task or research workflow is unavailable')
    control = db.scalar(select(AIExecutionControl).where(AIExecutionControl.name == 'primary').with_for_update())
    if control is None or not control.enabled:
        raise AIExecutionDenied('Global AI consent is disabled')
    policy = db.scalar(select(Policy).where(Policy.id == policy_id).with_for_update())
    allowed, _ = evaluate_policy(policy, 'AI_INFERENCE')
    if not allowed or policy is None or policy.rules_json.get('external_execution') is not False or policy.rules_json.get('ai_inference_allowed') is not True:
        raise AIExecutionDenied('Policy denies AI inference')
    if task.assigned_role != AI_TASK_ROLES[task.task_type]:
        raise AIExecutionDenied('Task role is not allowed for this AI handler')
    agent = db.scalar(select(Agent).where(Agent.role == task.assigned_role, Agent.enabled.is_(True)).with_for_update())
    profile = db.scalar(select(AIAgentProfile).where(AIAgentProfile.agent_id == agent.id).with_for_update()) if agent else None
    if profile is None or not profile.enabled:
        raise AIExecutionDenied('Agent AI profile is unavailable')
    provider = db.scalar(select(AIProvider).where(AIProvider.id == profile.provider_id).with_for_update())
    if provider is None or not provider.enabled or provider.archived or not provider.encrypted_api_key:
        raise AIExecutionDenied('Provider configuration or credential is unavailable')
    adapter = adapter_for(provider.kind, provider.base_url)
    if adapter is None:
        raise AIExecutionDenied('Provider adapter has not been verified for this endpoint')
    if profile.temperature is not None:
        raise AIExecutionDenied('Model temperature capability has not been verified')
    try:
        price_id = UUID(task.input_json['ai_price_id'])
        prompt_id = UUID(task.input_json['ai_prompt_version_id'])
    except (KeyError, ValueError, TypeError):
        raise AIExecutionDenied('AI task pricing and prompt versions are required') from None
    price = db.scalar(select(AIModelPrice).where(AIModelPrice.id == price_id, AIModelPrice.provider_id == provider.id, AIModelPrice.model_id == profile.model_id).with_for_update())
    prompt = db.scalar(select(AIPromptVersion).where(AIPromptVersion.id == prompt_id).with_for_update())
    now = datetime.now(UTC)
    if price is None or _aware(price.effective_at) > now or (price.expires_at is not None and _aware(price.expires_at) <= now):
        raise AIExecutionDenied('Model price version is unavailable or not effective')
    if (prompt is None or prompt.name != AI_TASK_PROMPTS[task.task_type] or prompt.constraints_json.get('provider_execution') is not True
        or prompt.constraints_json.get('tools') != [] or prompt.constraints_json.get('external_actions') is not False):
        raise AIExecutionDenied('Research prompt version is unavailable')
    research = db.scalar(select(AIResearchRun).where(AIResearchRun.id == workflow.research_run_id).with_for_update())
    if research is None or research.status != 'DRAFT':
        raise AIExecutionDenied('Research input is unavailable')
    is_content = task.task_type in CONTENT_TASKS
    if is_content != (research.kind == 'CONTENT') or (contract_for_prompt(prompt.name) is CONTENT_DRAFT) != is_content:
        raise AIExecutionDenied('AI task does not match its run kind')
    # Owner-rejected sources are never sent to a provider.
    sources = list(db.scalars(select(AIResearchSource).where(AIResearchSource.research_run_id == research.id, AIResearchSource.verification_status != 'REJECTED')
                              .order_by(AIResearchSource.id).limit(21)))
    if len(sources) > 20:
        raise AIExecutionDenied('Research context exceeds the source limit')
    output_context = None
    if is_content:
        spec = research.content_spec_json or {}
        try:
            request = ContentRequest.model_validate({**spec['request'], 'evidence': [
                {'source_id': str(source.id), 'verification_status': source.verification_status, 'text': source.excerpt} for source in sources]})
            output_context = {'content_types': list(request.content_types), 'expected_items': len(request.content_types) * request.count_per_type}
        except (KeyError, TypeError, ValueError):
            raise AIExecutionDenied('Content batch input is invalid') from None
    else:
        request = ResearchRequest(objective=research.objective, target_market=research.target_market, target_customers=research.target_customers,
                                  evidence=[EvidenceInput(source_id=source.id, text=source.excerpt) for source in sources], prior_outputs=_prior_outputs(db, task))
    template = PromptTemplate(prompt.name, prompt.version, prompt.system_text, prompt.developer_text)
    try:
        # Research requests keep the v29 wire format exactly (default research contract).
        wire = adapter.build(profile.model_id, template, request, profile.max_output_tokens, CONTENT_DRAFT) if is_content else adapter.build(profile.model_id, template, request, profile.max_output_tokens)
        endpoint = adapter.inference_url(profile.model_id)
    except ValueError:
        raise AIExecutionDenied('Model identifier or output limit is invalid for this provider') from None
    encoded_size = len(json.dumps(wire, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    # Conservative estimate only. Actual provider tokenization/billing can differ;
    # unknown charges must remain reserved rather than being assumed zero.
    input_ceiling = encoded_size + 1024
    pricing = Pricing(price.model_id, price.version, _aware(price.effective_at), Decimal(price.input_per_million), Decimal(price.output_per_million))
    estimate = pricing.ceiling(input_ceiling, profile.max_output_tokens)
    if estimate <= 0 or estimate > Decimal(profile.max_cost_usd) or estimate > Decimal(research.max_cost_usd):
        raise AIExecutionDenied('Estimated inference cost exceeds an approved run limit or is unverified')
    payload = {'workflow_id': str(workflow.id), 'workflow_version': workflow.version, 'task_id': str(task.id), 'task_type': task.task_type, 'assigned_role': task.assigned_role,
               'research_run_id': str(research.id), 'control_version': control.version, 'profile_id': str(profile.id),
               'provider_id': str(provider.id), 'provider_kind': provider.kind, 'model_id': profile.model_id,
               'credential_version': hashlib.sha256(provider.encrypted_api_key.encode()).hexdigest(),
               'price_id': str(price.id), 'price_version': price.version, 'prompt_version_id': str(prompt.id), 'prompt_version': prompt.version,
               'timeout_seconds': min(task.timeout_seconds, profile.timeout_seconds), 'max_output_tokens': profile.max_output_tokens,
               'estimated_input_tokens': input_ceiling, 'cost_estimate_usd': str(estimate), 'endpoint': endpoint, 'request': wire}
    payload['known_source_ids'] = [str(source.id) for source in sources]
    payload['verified_source_ids'] = [str(source.id) for source in sources if source.verification_status == 'VERIFIED']
    if is_content:
        payload['output_contract'] = CONTENT_DRAFT.name
        payload['output_context'] = output_context
    action = canonical_action('AI_INFERENCE', payload, 'workflow_task', task.id, policy.id, policy.version, 'ONCE')
    return action, action_hash(action)


def queue_ai_execution(db: Session, workflow_id: UUID, task_id: UUID, policy_id: UUID, authorization_id: UUID | None, actor: str, idempotency_key: str,
                       *, auto_run_id: UUID | None = None) -> TaskExecution:
    """Atomically consume one action approval and reserve one execution attempt.

    With ``auto_run_id`` the caller has already verified an ACTIVE workflow auto-run
    whose Owner-approved plan still matches; no per-task approval is consumed.
    Caller owns the transaction and must commit or roll back this operation as a
    whole. No provider is contacted here; the worker dispatches the PREPARED
    invocation only after claiming it with a fresh lease and rechecking controls.
    """
    if auto_run_id is None and actor != 'owner':
        raise AIExecutionDenied('Owner authorization is required')
    if (auto_run_id is None) == (authorization_id is None):
        raise AIExecutionDenied('Exactly one authorization source is required')
    action, digest = prepare_ai_action(db, workflow_id, task_id, policy_id)
    payload = action['action_payload']
    workflow = db.get(Workflow, workflow_id)
    task = db.get(WorkflowTask, task_id)
    if workflow.status != 'RUNNING' or task.status != 'READY' or task.max_retries != 0:
        raise AIExecutionDenied('AI task state is invalid or automatic paid retries are configured')
    unfinished = db.scalar(select(func.count()).select_from(TaskDependency).join(WorkflowTask, WorkflowTask.id == TaskDependency.depends_on_task_id).where(TaskDependency.task_id == task_id, WorkflowTask.status != 'SUCCEEDED')) or 0
    if unfinished:
        raise AIExecutionDenied('AI task dependencies are incomplete')
    research = db.get(AIResearchRun, UUID(payload['research_run_id']))
    reservations = list(db.scalars(select(BudgetReservation).join(AIInvocation, AIInvocation.reservation_id == BudgetReservation.id).where(AIInvocation.research_run_id == research.id)))
    committed = sum((Decimal(item.actual_amount) if item.status in {'SETTLED', 'RELEASED'} and item.actual_amount is not None else Decimal(item.reserved_amount) for item in reservations), Decimal('0'))
    estimate = Decimal(payload['cost_estimate_usd'])
    if committed + estimate > Decimal(research.max_cost_usd):
        raise AIExecutionDenied('Research run cost limit is exhausted')
    if auto_run_id is None and not consume_action_authorization(db, authorization_id, digest, actor):
        raise AIExecutionDenied('AI action approval is missing, expired, consumed or mismatched')
    execution_id = uuid4()
    try:
        reservation = create_reservation(db, execution_id, f'ai-execution:{execution_id}', estimate,
                                         datetime.now(UTC) + timedelta(seconds=max(payload['timeout_seconds'] + 60, 300)), actor)
    except ValueError as error:
        raise AIExecutionDenied(str(error)) from None
    attempt = (db.scalar(select(func.max(TaskExecution.attempt_number)).where(TaskExecution.task_id == task.id)) or 0) + 1
    execution = TaskExecution(id=execution_id, task_id=task.id, attempt_number=attempt, status='QUEUED', idempotency_key=idempotency_key,
                              policy_id=policy_id, authorization_id=authorization_id, auto_run_id=auto_run_id, action_hash=digest, input_snapshot_json=payload)
    db.add(execution)
    db.flush()
    invocation = AIInvocation(execution_id=execution.id, research_run_id=research.id, provider_id=UUID(payload['provider_id']),
                              profile_id=UUID(payload['profile_id']), prompt_version_id=UUID(payload['prompt_version_id']),
                              price_id=UUID(payload['price_id']), reservation_id=reservation.id, status='PREPARED',
                              model_id=payload['model_id'], agent_role=task.assigned_role, request_snapshot_json=payload['request'], estimated_cost=estimate)
    db.add(invocation)
    validate_transition(TASK_TRANSITIONS, task.status, 'RUNNING')
    task.status = 'RUNNING'
    db.flush()
    db.add(WorkflowEvent(workflow_id=workflow.id, task_id=task.id, event_type='AI_EXECUTION_PREPARED', previous_status='READY', new_status='RUNNING', actor=actor,
                         metadata_json={'execution_id': str(execution.id), 'invocation_id': str(invocation.id), 'reservation_id': str(reservation.id)}))
    db.add(AuditEvent(actor=actor, action='ai_invocation.prepared', entity_type='ai_invocation', entity_id=invocation.id,
                      detail={'workflow_id': str(workflow.id), 'task_id': str(task.id), 'execution_id': str(execution.id), 'reservation_id': str(reservation.id), 'estimated_cost': str(estimate)}))
    return execution


def dispatch_invocation(factory, execution_id: UUID, lease_token: UUID, *, transport=None):
    """Recheck controls, durably mark one dispatch, then perform one provider call.

    A crash after DISPATCHED leaves an uncertain billing outcome. This operation
    never redispatches a DISPATCHED invocation and never releases its reservation.
    The worker calls this only for a claimed AI task with a valid lease.
    """
    if transport is None:
        transport = post_provider_json
    with factory.begin() as db:
        task_id = db.scalar(select(TaskExecution.task_id).where(TaskExecution.id == execution_id))
        task = db.get(WorkflowTask, task_id) if task_id else None
        if task is None:
            raise AIExecutionDenied('AI execution not found')
        action, digest = prepare_ai_action(db, task.workflow_id, task.id, db.get(TaskExecution, execution_id).policy_id)
        execution = db.scalar(select(TaskExecution).where(TaskExecution.id == execution_id).with_for_update())
        invocation = db.scalar(select(AIInvocation).where(AIInvocation.execution_id == execution_id).with_for_update())
        workflow = db.get(Workflow, task.workflow_id)
        if (execution.status != 'RUNNING' or execution.lease_token != lease_token or execution.lease_expires_at is None
            or is_expired(execution.lease_expires_at) or task.status != 'RUNNING' or workflow.status != 'RUNNING'
            or invocation is None or invocation.status != 'PREPARED' or execution.action_hash != digest
            or execution.input_snapshot_json != action['action_payload']):
            raise AIExecutionDenied('AI execution state, lease or snapshot is invalid')
        if execution.auto_run_id is not None:
            from app.orchestration.auto_run import AutoRunDenied, verify_auto_run
            try:
                verify_auto_run(db, execution.auto_run_id, workflow, in_flight=True)
            except AutoRunDenied:
                raise AIExecutionDenied('AI execution authorization is invalid') from None
        else:
            authorization = db.scalar(select(ActionAuthorization).where(ActionAuthorization.id == execution.authorization_id).with_for_update())
            approval = db.get(ApprovalRequest, authorization.approval_id) if authorization else None
            if (authorization is None or approval is None or authorization.status != 'CONSUMED' or approval.status != 'CONSUMED'
                or authorization.action_hash != digest or approval.action_hash != digest
                or is_expired(authorization.expires_at) or is_expired(approval.expires_at)):
                raise AIExecutionDenied('AI execution authorization is invalid')
        unfinished = db.scalar(select(func.count()).select_from(TaskDependency).join(WorkflowTask, WorkflowTask.id == TaskDependency.depends_on_task_id).where(TaskDependency.task_id == task.id, WorkflowTask.status != 'SUCCEEDED')) or 0
        if unfinished:
            raise AIExecutionDenied('AI dependencies are incomplete')
        initial_reservation = db.get(BudgetReservation, invocation.reservation_id)
        account = db.scalar(select(BudgetAccount).where(BudgetAccount.id == initial_reservation.budget_account_id).with_for_update()) if initial_reservation else None
        now = datetime.now(UTC)
        if (account is None or account.status != 'ACTIVE' or account.currency != 'USD'
            or not _aware(account.period_start) <= now < _aware(account.period_end)
            or committed_amount(db, account.id) > Decimal(account.limit_amount) - Decimal(account.reserve_amount)):
            raise AIExecutionDenied('AI budget account is unavailable or overcommitted')
        reservation = db.scalar(select(BudgetReservation).where(BudgetReservation.id == invocation.reservation_id).with_for_update())
        if (reservation is None or reservation.status != 'ACTIVE' or is_expired(reservation.expires_at)
            or reservation.task_id != execution.id or Decimal(reservation.reserved_amount) < Decimal(invocation.estimated_cost)):
            raise AIExecutionDenied('AI reservation is missing, expired, closed or insufficient')
        research = db.get(AIResearchRun, invocation.research_run_id)
        run_reservations = list(db.scalars(select(BudgetReservation).join(AIInvocation, AIInvocation.reservation_id == BudgetReservation.id).where(AIInvocation.research_run_id == research.id)))
        run_committed = sum((Decimal(item.actual_amount) if item.status in {'SETTLED', 'RELEASED'} and item.actual_amount is not None else Decimal(item.reserved_amount) for item in run_reservations), Decimal('0'))
        if run_committed > Decimal(research.max_cost_usd):
            raise AIExecutionDenied('Research run budget is overcommitted')
        provider = db.get(AIProvider, invocation.provider_id)
        credential = decrypt_credential(provider.id, provider.encrypted_api_key)
        payload = action['action_payload']
        request_payload = payload['request']
        timeout = payload['timeout_seconds']
        adapter = adapter_for(provider.kind, provider.base_url)
        if adapter is None or payload['endpoint'] != adapter.inference_url(payload['model_id']):
            raise AIExecutionDenied('Provider adapter has not been verified for this endpoint')
        known_sources = {UUID(value) for value in payload['known_source_ids']}
        verified_sources = {UUID(value) for value in payload['verified_source_ids']}
        try:
            contract = contract_named(payload.get('output_contract'))
        except ValueError:
            raise AIExecutionDenied('Output contract is unknown') from None
        invocation.status = 'DISPATCHED'
        invocation.started_at = datetime.now(UTC)
        db.add(AuditEvent(actor='ai-worker', action='ai_invocation.dispatched', entity_type='ai_invocation', entity_id=invocation.id,
                          detail={'execution_id': str(execution.id), 'workflow_id': str(workflow.id), 'task_id': str(task.id)}))
    # No database transaction is held while waiting on a remote provider. No
    # inference tools, provider fallback or automatic request retries are enabled.
    try:
        try:
            status, raw = transport(payload['endpoint'], {adapter.host}, adapter.headers(credential), request_payload, timeout)
        except Exception:
            raise ProviderOutputError('PROVIDER_OUTCOME_UNKNOWN') from None
        finally:
            credential = None
        if not 200 <= status < 300:
            raise ProviderOutputError('PROVIDER_HTTP_OUTCOME_UNKNOWN')
        result = adapter.parse(raw, known_sources, verified_sources, contract, payload.get('output_context'))
    except ProviderOutputError as error:
        record_outcome(factory, execution_id, None, error)
        raise
    record_outcome(factory, execution_id, result, None)
    return result
