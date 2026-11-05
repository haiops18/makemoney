"""Fail-closed transaction-bound task authorization primitives.

This module does not start tasks. The caller must hold the transaction through
the execution claim and commit; authorization consumption rolls back on failure.
"""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.approvals.service import consume_action_authorization, evaluate_policy
from app.core.action_hash import action_hash, canonical_action
from app.db.models import Agent, AIResearchRun, AIResearchSource, Opportunity, OpportunityEvidence, Policy, TaskDependency, Workflow, WorkflowTask


class GateDenied(ValueError):
    """A control could not be verified; execution must not proceed."""


def task_action(db: Session, workflow_id: UUID, task_id: UUID, policy_id: UUID) -> tuple[dict, str]:
    workflow = db.scalar(select(Workflow).where(Workflow.id == workflow_id).with_for_update())
    if workflow is None:
        raise GateDenied('Workflow not found')
    task = db.scalar(select(WorkflowTask).where(WorkflowTask.id == task_id, WorkflowTask.workflow_id == workflow_id).with_for_update())
    if task is None:
        raise GateDenied('Task not found in workflow')
    policy = db.scalar(select(Policy).where(Policy.id == policy_id).with_for_update())
    allowed, reason = evaluate_policy(policy, 'INTERNAL_WORKFLOW')
    if not allowed or policy is None or policy.rules_json.get('external_execution') is not False:
        raise GateDenied(reason if not allowed else 'External-execution policy must be explicitly disabled')
    if task.task_type not in {'VALIDATE_OPPORTUNITY', 'VALIDATE_EVIDENCE', 'VALIDATE_RESEARCH_DRAFT'}:
        raise GateDenied('Handler is not allowlisted')
    if not db.scalar(select(Agent.id).where(Agent.role == task.assigned_role, Agent.enabled.is_(True)).with_for_update()):
        raise GateDenied('Assigned role is unavailable')
    if task.task_type == 'VALIDATE_RESEARCH_DRAFT':
        research = db.scalar(select(AIResearchRun).where(AIResearchRun.id == workflow.research_run_id).with_for_update())
        if research is None or research.status != 'DRAFT':
            raise GateDenied('Research draft is unavailable')
        source_count = db.scalar(select(func.count()).select_from(AIResearchSource).where(AIResearchSource.research_run_id == research.id)) or 0
        handler_input = {'objective': research.objective, 'target_market': research.target_market, 'source_count': source_count}
    else:
        opportunity = db.scalar(select(Opportunity).where(Opportunity.id == workflow.opportunity_id).with_for_update())
        if opportunity is None or opportunity.status in {'DISQUALIFIED', 'ARCHIVED'}:
            raise GateDenied('Opportunity is unavailable or disqualified')
        if task.task_type == 'VALIDATE_OPPORTUNITY':
            handler_input = {'title': opportunity.title, 'business_model': opportunity.business_model, 'target_market': opportunity.target_market}
        else:
            evidence_count = db.scalar(select(func.count()).select_from(OpportunityEvidence).where(OpportunityEvidence.opportunity_id == opportunity.id)) or 0
            verified_count = db.scalar(select(func.count()).select_from(OpportunityEvidence).where(OpportunityEvidence.opportunity_id == opportunity.id, OpportunityEvidence.verification_status == 'VERIFIED')) or 0
            handler_input = {'evidence_count': evidence_count, 'verified_count': verified_count}
    payload = {'workflow_id': str(workflow.id), 'workflow_version': workflow.version, 'task_id': str(task.id), 'task_type': task.task_type, 'assigned_role': task.assigned_role, 'handler_input': handler_input, 'cost_usd': '0'}
    action = canonical_action('INTERNAL_WORKFLOW', payload, 'workflow_task', task.id, policy.id, policy.version, 'ONCE')
    return action, action_hash(action)


def authorize_task(db: Session, workflow_id: UUID, task_id: UUID, policy_id: UUID, authorization_id: UUID, actor: str) -> dict:
    if actor != 'owner':
        raise GateDenied('Owner authorization required')
    action, expected_hash = task_action(db, workflow_id, task_id, policy_id)
    workflow = db.get(Workflow, workflow_id)
    task = db.get(WorkflowTask, task_id)
    if workflow is None or workflow.status != 'RUNNING' or task is None or task.status != 'READY':
        raise GateDenied('Workflow or task state does not permit execution')
    unfinished = db.scalar(select(func.count()).select_from(TaskDependency).join(WorkflowTask, WorkflowTask.id == TaskDependency.depends_on_task_id).where(TaskDependency.task_id == task_id, WorkflowTask.status != 'SUCCEEDED')) or 0
    if unfinished:
        raise GateDenied('Dependencies are not complete')
    # Only pure, fixed-cost-zero handlers above are allowed. No paid task
    # is admitted here; adding one requires an explicit reservation gate first.
    if not consume_action_authorization(db, authorization_id, expected_hash, actor):
        raise GateDenied('Approval is missing, expired, consumed or mismatched')
    return action['action_payload']['handler_input']
