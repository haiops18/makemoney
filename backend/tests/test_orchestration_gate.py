from uuid import uuid4
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models import ActionAuthorization, ApprovalRequest, Opportunity, Policy, Workflow, WorkflowTask
from app.db.session import get_db
from app.main import app
from app.orchestration.gate import GateDenied, authorize_task, task_action


def test_gate_denies_missing_approval_and_binds_current_data(client):
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        policy = db.scalar(select(Policy))
        opportunity = Opportunity(title='Research', business_model='MICRO_SAAS', created_by='owner')
        db.add(opportunity)
        db.flush()
        workflow = Workflow(opportunity_id=opportunity.id, name='Test', created_by='owner', status='RUNNING')
        db.add(workflow)
        db.flush()
        task = WorkflowTask(workflow_id=workflow.id, name='Validate', task_type='VALIDATE_OPPORTUNITY', assigned_role='research', status='READY', input_json={})
        db.add(task)
        db.flush()
        _, before = task_action(db, workflow.id, task.id, policy.id)
        with pytest.raises(GateDenied, match='Approval'):
            authorize_task(db, workflow.id, task.id, policy.id, uuid4(), 'owner')
        with pytest.raises(GateDenied, match='Owner'):
            authorize_task(db, workflow.id, task.id, policy.id, uuid4(), 'other')
        opportunity.title = 'Changed input'
        db.flush()
        _, after = task_action(db, workflow.id, task.id, policy.id)
        assert before != after
        policy.enabled = False
        db.flush()
        with pytest.raises(GateDenied):
            task_action(db, workflow.id, task.id, policy.id)
    finally:
        db.rollback()
        generator.close()


def test_exact_approval_is_consumed_once_in_caller_transaction(client):
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        policy = db.scalar(select(Policy))
        opportunity = Opportunity(title='Research', business_model='MICRO_SAAS', created_by='owner')
        db.add(opportunity)
        db.flush()
        workflow = Workflow(opportunity_id=opportunity.id, name='Test', created_by='owner', status='RUNNING')
        db.add(workflow)
        db.flush()
        task = WorkflowTask(workflow_id=workflow.id, name='Validate', task_type='VALIDATE_OPPORTUNITY', assigned_role='research', status='READY', input_json={})
        db.add(task)
        db.flush()
        action, digest = task_action(db, workflow.id, task.id, policy.id)
        expires = datetime.now(UTC) + timedelta(minutes=5)
        approval = ApprovalRequest(policy_id=policy.id, policy_version=policy.version, action_type='INTERNAL_WORKFLOW', action_hash=digest, action_payload_json=action['action_payload'], resource_type='workflow_task', resource_id=task.id, requested_by='owner', status='APPROVED', expires_at=expires)
        db.add(approval)
        db.flush()
        authorization = ActionAuthorization(approval_id=approval.id, action_hash=digest, scope='ONCE', status='ACTIVE', expires_at=expires)
        db.add(authorization)
        db.flush()
        result = authorize_task(db, workflow.id, task.id, policy.id, authorization.id, 'owner')
        assert result['title'] == 'Research'
        assert authorization.status == 'CONSUMED'
        with pytest.raises(GateDenied, match='Approval'):
            authorize_task(db, workflow.id, task.id, policy.id, authorization.id, 'owner')
        db.rollback()
    finally:
        db.rollback()
        generator.close()
