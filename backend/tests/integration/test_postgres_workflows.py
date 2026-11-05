import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import ApprovalRequest, AuditEvent, Opportunity, TaskDependency, TaskExecution, Workflow, WorkflowEvent, WorkflowTask
from app.db.session import get_db
from app.main import app


@pytest.mark.postgres
def test_workflow_constraints_and_transaction_rollback():
    from sqlalchemy.exc import IntegrityError
    url = os.getenv('POSTGRES_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Isolated PostgreSQL required')
    engine = create_engine(url)
    with Session(engine, expire_on_commit=False) as db:
        opportunity = Opportunity(title='Constraint test', business_model='MICRO_SAAS', created_by='owner')
        db.add(opportunity); db.flush()
        first = Workflow(name='First', opportunity_id=opportunity.id, created_by='owner')
        second = Workflow(name='Second', opportunity_id=opportunity.id, created_by='owner')
        db.add_all([first, second]); db.flush()
        task1 = WorkflowTask(workflow_id=first.id, name='One', task_type='VALIDATE_OPPORTUNITY', assigned_role='research', input_json={})
        task2 = WorkflowTask(workflow_id=second.id, name='Two', task_type='VALIDATE_OPPORTUNITY', assigned_role='research', input_json={})
        db.add_all([task1, task2]); db.commit()
        db.add(TaskDependency(workflow_id=first.id, task_id=task1.id, depends_on_task_id=task2.id))
        with pytest.raises(IntegrityError): db.commit()
        db.rollback()
        db.add(TaskDependency(workflow_id=first.id, task_id=task1.id, depends_on_task_id=task1.id))
        with pytest.raises(IntegrityError): db.commit()
        db.rollback()
        db.add(WorkflowEvent(workflow_id=first.id, task_id=task2.id, event_type='INVALID', actor='test', metadata_json={}))
        with pytest.raises(IntegrityError): db.commit()
        db.rollback()
        assert db.get(Workflow, first.id).status == 'DRAFT'
        db.add(TaskExecution(task_id=task1.id, attempt_number=1, status='FAILED', idempotency_key='constraint-' + str(uuid4())))
        db.commit()
        db.add(TaskExecution(task_id=task1.id, attempt_number=1, status='FAILED', idempotency_key='constraint-' + str(uuid4())))
        with pytest.raises(IntegrityError): db.commit()
        db.rollback()


@pytest.mark.postgres
def test_concurrent_workflow_starts_consume_one_approval():
    url = os.getenv('POSTGRES_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Isolated PostgreSQL required')
    engine = create_engine(url)
    def database():
        with Session(engine, expire_on_commit=False, autoflush=False) as session:
            yield session
    app.dependency_overrides[get_db] = database
    suffix = str(uuid4())
    auth = {'Authorization': 'Bearer test-owner-key'}
    def headers(label):
        return {**auth, 'Idempotency-Key': suffix + label}
    try:
        with TestClient(app) as client:
            opportunity = client.post('/api/v1/opportunities', json={'title': 'Concurrent workflow', 'business_model': 'MICRO_SAAS'}, headers=headers('opp')).json()
            workflow = client.post('/api/v1/workflows', json={'name': 'Concurrent', 'opportunity_id': opportunity['id']}, headers=headers('workflow')).json()
            path = '/api/v1/workflows/' + workflow['id']
            task = client.post(path + '/tasks', json={'name': 'Validate', 'task_type': 'VALIDATE_OPPORTUNITY', 'assigned_role': 'research'}, headers=headers('task'))
            assert task.status_code == 201, task.text
            policy = next(item for item in client.get('/api/v1/policies', headers=auth).json() if item['enabled'] and 'INTERNAL_WORKFLOW' in item['rules_json']['allowed_action_types'])
            submission = client.post(path + '/submit', json={'policy_id': policy['id'], 'expires_at': (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}, headers=headers('submit'))
            assert submission.status_code == 200, submission.text
            approval_id = submission.json()['approval_id']
            assert client.post('/api/v1/approvals/' + approval_id + '/approve', json={'reason': 'Owner approved'}, headers=headers('approve')).status_code == 200
        def start(index):
            with TestClient(app) as client:
                return client.post(path + '/start', headers=headers('start' + str(index))).status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(start, range(2))) == [200, 409]
        with Session(engine) as session:
            assert session.get(Workflow, UUID(workflow['id'])).status == 'QUEUED'
            assert session.get(ApprovalRequest, UUID(approval_id)).status == 'CONSUMED'
            assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == UUID(approval_id), AuditEvent.action == 'authorization.consumed')) == 0
            assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'authorization.consumed', AuditEvent.detail['approval_id'].as_string() == approval_id)) == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.postgres
def test_worker_claim_fencing_and_expired_lease_recovery(monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from app.orchestration.worker import activate_one, claim_one, finalize, recover_one, run_once

    url = os.getenv('POSTGRES_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Isolated PostgreSQL required')
    engine = create_engine(url)
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    def database():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db] = database
    suffix = str(uuid4())
    auth = {'Authorization': 'Bearer test-owner-key'}
    def headers(label):
        return {**auth, 'Idempotency-Key': suffix + label}
    def approve_task(client, path, task_id, policy_id, label):
        prepared = client.get(f'{path}/tasks/{task_id}/approval-action', params={'policy_id': policy_id}, headers=auth)
        assert prepared.status_code == 200, prepared.text
        action = prepared.json()['action']
        body = {key: action[key] for key in ('policy_id', 'action_type', 'action_payload', 'resource_type', 'resource_id', 'scope')}
        body['expires_at'] = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        created = client.post('/api/v1/approvals', json=body, headers=headers(label + 'create'))
        assert created.status_code == 201, created.text
        approval_id = created.json()['id']
        decision = client.post('/api/v1/approvals/' + approval_id + '/approve', json={'reason': 'Owner reviewed exact task'}, headers=headers(label + 'approve'))
        assert decision.status_code == 200, decision.text
        return approval_id
    try:
        with TestClient(app) as client:
            opportunity = client.post('/api/v1/opportunities', json={'title': 'Worker test', 'business_model': 'MICRO_SAAS', 'target_market': 'Owner supplied'}, headers=headers('opp')).json()
            workflow = client.post('/api/v1/workflows', json={'name': 'Lease test', 'opportunity_id': opportunity['id']}, headers=headers('workflow')).json()
            path = '/api/v1/workflows/' + workflow['id']
            task = client.post(path + '/tasks', json={'name': 'Validate', 'task_type': 'VALIDATE_OPPORTUNITY', 'assigned_role': 'research', 'max_retries': 2}, headers=headers('task'))
            assert task.status_code == 201, task.text
            task_id = task.json()['id']
            policy_id = next(item['id'] for item in client.get('/api/v1/policies', headers=auth).json() if item['enabled'] and 'INTERNAL_WORKFLOW' in item['rules_json']['allowed_action_types'])
            submitted = client.post(path + '/submit', json={'policy_id': policy_id, 'expires_at': (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}, headers=headers('submit'))
            assert submitted.status_code == 200, submitted.text
            approval_id = submitted.json()['approval_id']
            assert client.post('/api/v1/approvals/' + approval_id + '/approve', json={'reason': 'Owner review'}, headers=headers('approve')).status_code == 200
            assert client.post(path + '/start', headers=headers('start')).status_code == 200
            for _ in range(100):
                if client.get(path, headers=auth).json()['status'] == 'RUNNING':
                    break
                assert activate_one(factory)
            assert client.get(path + '/tasks', headers=auth).json()[0]['status'] == 'READY'
            task_approval = approve_task(client, path, task_id, policy_id, 'taskapproval1')
            queue_body = {'policy_id': policy_id, 'approval_id': task_approval}
            def queue_attempt(index):
                with TestClient(app) as concurrent_client:
                    return index, concurrent_client.post(f'{path}/tasks/{task_id}/queue', json=queue_body, headers=headers('queue1-' + str(index)))
            with ThreadPoolExecutor(max_workers=2) as executor:
                attempts = list(executor.map(queue_attempt, range(2)))
            assert sorted(result.status_code for _, result in attempts) == [201, 403]
            winning_index, queued = next((index, result) for index, result in attempts if result.status_code == 201)
            assert client.post(f'{path}/tasks/{task_id}/queue', json=queue_body, headers=headers('queue1-' + str(winning_index))).json()['id'] == queued.json()['id']
            with ThreadPoolExecutor(max_workers=2) as executor:
                claims = list(executor.map(lambda _: claim_one(factory), range(2)))
            actual = [claim for claim in claims if claim is not None]
            assert len(actual) == 1
            execution_id, token, *_ = actual[0]
            with factory.begin() as db:
                db.get(TaskExecution, execution_id).lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            assert recover_one(factory)
            assert not finalize(factory, execution_id, token, {'status': 'COMPLETE', 'missing': []}, None)
            with factory.begin() as db:
                execution = db.get(TaskExecution, execution_id)
                task_row = db.get(WorkflowTask, UUID(task_id))
                assert execution.status == 'ABANDONED'
                assert task_row.status == 'RETRY_WAIT'
                task_row.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
            # A recovered attempt cannot reuse a consumed task approval.
            rejected = client.post(f'{path}/tasks/{task_id}/queue', json=queue_body, headers=headers('reuse'))
            assert rejected.status_code == 403, rejected.text
            fresh_approval = approve_task(client, path, task_id, policy_id, 'taskapproval2')
            retried = client.post(f'{path}/tasks/{task_id}/queue', json={'policy_id': policy_id, 'approval_id': fresh_approval}, headers=headers('queue2'))
            assert retried.status_code == 201, retried.text
            assert retried.json()['attempt_number'] == 2
            with monkeypatch.context() as patch:
                patch.setattr('app.orchestration.worker._invoke', lambda *_: (None, TimeoutError('test-only timeout')))
                assert run_once(factory)
            with factory.begin() as db:
                task_row = db.get(WorkflowTask, UUID(task_id))
                assert task_row.status == 'RETRY_WAIT'
                task_row.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
            third_approval = approve_task(client, path, task_id, policy_id, 'taskapproval-timeout-retry')
            third = client.post(f'{path}/tasks/{task_id}/queue', json={'policy_id': policy_id, 'approval_id': third_approval}, headers=headers('queue-after-timeout'))
            assert third.status_code == 201, third.text
            assert third.json()['attempt_number'] == 3
            assert run_once(factory)
            assert client.get(path, headers=auth).json()['status'] == 'COMPLETED'
            history = client.get(path + '/executions', headers=auth).json()
            assert {item['status'] for item in history} == {'ABANDONED', 'TIMED_OUT', 'SUCCEEDED'}

            second = client.post('/api/v1/workflows', json={'name': 'Cancellation race', 'opportunity_id': opportunity['id']}, headers=headers('workflow2')).json()
            path2 = '/api/v1/workflows/' + second['id']
            second_task = client.post(path2 + '/tasks', json={'name': 'Validate', 'task_type': 'VALIDATE_OPPORTUNITY', 'assigned_role': 'research'}, headers=headers('task2')).json()
            submitted2 = client.post(path2 + '/submit', json={'policy_id': policy_id, 'expires_at': (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}, headers=headers('submit2')).json()
            assert client.post('/api/v1/approvals/' + submitted2['approval_id'] + '/approve', json={'reason': 'Owner review'}, headers=headers('approve2')).status_code == 200
            assert client.post(path2 + '/start', headers=headers('start2')).status_code == 200
            for _ in range(100):
                if client.get(path2, headers=auth).json()['status'] == 'RUNNING':
                    break
                assert activate_one(factory)
            approval2 = approve_task(client, path2, second_task['id'], policy_id, 'taskapproval3')
            assert client.post(f"{path2}/tasks/{second_task['id']}/queue", json={'policy_id': policy_id, 'approval_id': approval2}, headers=headers('queue3')).status_code == 201
            running = claim_one(factory)
            assert running is not None
            cancelled = client.post(path2 + '/cancel', headers=headers('cancel'))
            assert cancelled.json()['status'] == 'CANCELLED'
            assert finalize(factory, running[0], running[1], {'status': 'COMPLETE', 'missing': []}, None)
            assert client.get(path2 + '/tasks', headers=auth).json()[0]['status'] == 'CANCELLED'
            cancelled_history = client.get(path2 + '/executions', headers=auth).json()
            assert cancelled_history[0]['status'] == 'CANCELLED'
            assert cancelled_history[0]['output_json'] is None
    finally:
        app.dependency_overrides.clear()
