def test_owner_draft_and_task_creation_are_idempotent_and_audited(client, auth_headers):
    assert client.get('/api/v1/workflows').status_code == 401
    opportunity = client.post('/api/v1/opportunities', json={'title': 'Workflow input', 'business_model': 'MICRO_SAAS'}, headers={**auth_headers, 'Idempotency-Key': 'workflow-input'}).json()
    headers = {**auth_headers, 'Idempotency-Key': 'workflow-create'}
    body = {'opportunity_id': opportunity['id'], 'name': 'Controlled workflow'}
    created = client.post('/api/v1/workflows', json=body, headers=headers)
    assert created.status_code == 201, created.text
    workflow = created.json()
    assert workflow['status'] == 'DRAFT'
    assert client.post('/api/v1/workflows', json=body, headers=headers).json()['id'] == workflow['id']
    assert client.post('/api/v1/workflows', json={**body, 'name': 'different'}, headers=headers).status_code == 409
    path = '/api/v1/workflows/' + workflow['id'] + '/tasks'
    task_headers = {**auth_headers, 'Idempotency-Key': 'workflow-task'}
    task_body = {'name': 'Validate', 'task_type': 'VALIDATE_OPPORTUNITY', 'assigned_role': 'research'}
    result = client.post(path, json=task_body, headers=task_headers)
    assert result.status_code == 201, result.text
    assert client.post(path, json=task_body, headers=task_headers).json()['id'] == result.json()['id']
    bad = {**task_body, 'task_type': 'SHELL'}
    assert client.post(path, json=bad, headers={**auth_headers, 'Idempotency-Key': 'unknown-handler'}).status_code == 422
    assert len(client.get(path, headers=auth_headers).json()) == 1
    listed = client.get('/api/v1/workflows', params={'search': 'Controlled', 'assigned_role': 'research'}, headers=auth_headers).json()
    assert listed['total'] == 1 and listed['items'][0]['task_count'] == 1
    assert client.get('/api/v1/workflows/summary', headers=auth_headers).json()['total_tasks'] == 1
    policy_id = client.get('/api/v1/policies', headers=auth_headers).json()[0]['id']
    prepared = client.get(path + '/' + result.json()['id'] + '/approval-action', params={'policy_id': policy_id}, headers=auth_headers)
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()['action']['action_payload']['cost_usd'] == '0'
    assert prepared.json()['action']['resource_id'] == result.json()['id']
    events = client.get('/api/v1/audit-events', headers=auth_headers).json()
    assert any(event['action'] == 'workflow.created' for event in events)
    assert any(event['action'] == 'workflow.task_created' for event in events)
    assert client.post('/api/v1/workflows/' + workflow['id'] + '/start', headers={**auth_headers, 'Idempotency-Key': 'start'}).status_code == 409


def test_workflow_start_requires_exact_owner_approval(client, auth_headers):
    from datetime import UTC, datetime, timedelta
    opportunity = client.post('/api/v1/opportunities', json={'title': 'Approval input', 'business_model': 'MICRO_SAAS'}, headers={**auth_headers, 'Idempotency-Key': 'approval-input'}).json()
    workflow = client.post('/api/v1/workflows', json={'opportunity_id': opportunity['id'], 'name': 'Review'}, headers={**auth_headers, 'Idempotency-Key': 'approval-workflow'}).json()
    base = '/api/v1/workflows/' + workflow['id']
    task = client.post(base + '/tasks', json={'name': 'Validate', 'task_type': 'VALIDATE_OPPORTUNITY', 'assigned_role': 'research'}, headers={**auth_headers, 'Idempotency-Key': 'approval-task'})
    assert task.status_code == 201
    policy_id = client.get('/api/v1/policies', headers=auth_headers).json()[0]['id']
    body = {'policy_id': policy_id, 'expires_at': (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}
    submission = client.post(base + '/submit', json=body, headers={**auth_headers, 'Idempotency-Key': 'submit'})
    assert submission.status_code == 200, submission.text
    assert submission.json()['workflow']['status'] == 'PENDING_APPROVAL'
    assert client.post(base + '/start', headers={**auth_headers, 'Idempotency-Key': 'denied-start'}).status_code == 403
    approval_id = submission.json()['approval_id']
    approved = client.post('/api/v1/approvals/' + approval_id + '/approve', json={'reason': 'Owner review'}, headers={**auth_headers, 'Idempotency-Key': 'approval-decision'})
    assert approved.status_code == 200, approved.text
    headers = {**auth_headers, 'Idempotency-Key': 'allowed-start'}
    started = client.post(base + '/start', headers=headers)
    assert started.status_code == 200, started.text
    assert started.json()['status'] == 'QUEUED'
    assert client.post(base + '/start', headers=headers).json() == started.json()
    assert client.post(base + '/start', headers={**auth_headers, 'Idempotency-Key': 'another-start'}).status_code == 409
    assert client.patch(base, json={'name': 'changed after approval'}, headers={**auth_headers, 'Idempotency-Key': 'locked-edit'}).status_code == 409
    paused = client.post(base + '/pause', headers={**auth_headers, 'Idempotency-Key': 'pause'})
    assert paused.json()['status'] == 'PAUSED'
    resumed = client.post(base + '/resume', headers={**auth_headers, 'Idempotency-Key': 'resume'})
    assert resumed.json()['status'] == 'QUEUED'
    cancelled = client.post(base + '/cancel', headers={**auth_headers, 'Idempotency-Key': 'cancel'})
    assert cancelled.json()['status'] == 'CANCELLED'
    assert client.get(base + '/tasks', headers=auth_headers).json()[0]['status'] == 'CANCELLED'
    assert client.post(base + '/resume', headers={**auth_headers, 'Idempotency-Key': 'resume-cancelled'}).status_code == 409
    assert client.get(base + '/executions', headers=auth_headers).json() == []
    events = client.get(base + '/events', headers=auth_headers).json()
    assert any(event['new_status'] == 'CANCELLED' for event in events)


def test_workflow_start_rejects_content_changed_after_approval(client, auth_headers):
    from datetime import UTC, datetime, timedelta
    from uuid import UUID
    from app.db.models import Workflow
    from app.db.session import get_db
    from app.main import app

    opportunity = client.post('/api/v1/opportunities', json={'title': 'Changed input', 'business_model': 'MICRO_SAAS'}, headers={**auth_headers, 'Idempotency-Key': 'changed-input'}).json()
    workflow = client.post('/api/v1/workflows', json={'opportunity_id': opportunity['id'], 'name': 'Review'}, headers={**auth_headers, 'Idempotency-Key': 'changed-workflow'}).json()
    base = '/api/v1/workflows/' + workflow['id']
    assert client.post(base + '/tasks', json={'name': 'Validate', 'task_type': 'VALIDATE_OPPORTUNITY', 'assigned_role': 'research'}, headers={**auth_headers, 'Idempotency-Key': 'changed-task'}).status_code == 201
    policy_id = client.get('/api/v1/policies', headers=auth_headers).json()[0]['id']
    submitted = client.post(base + '/submit', json={'policy_id': policy_id, 'expires_at': (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}, headers={**auth_headers, 'Idempotency-Key': 'changed-submit'}).json()
    assert client.post('/api/v1/approvals/' + submitted['approval_id'] + '/approve', json={'reason': 'Approved original'}, headers={**auth_headers, 'Idempotency-Key': 'changed-approve'}).status_code == 200
    generator = app.dependency_overrides[get_db]()
    session = next(generator)
    session.get(Workflow, UUID(workflow['id'])).version += 1
    session.commit()
    generator.close()
    result = client.post(base + '/start', headers={**auth_headers, 'Idempotency-Key': 'changed-start'})
    assert result.status_code == 403
    assert client.get(base, headers=auth_headers).json()['status'] == 'PENDING_APPROVAL'
    reopened = client.post(base + '/reopen', headers={**auth_headers, 'Idempotency-Key': 'changed-reopen'})
    assert reopened.status_code == 200 and reopened.json()['status'] == 'DRAFT'
    replacement = client.post(base + '/submit', json={'policy_id': policy_id, 'expires_at': (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}, headers={**auth_headers, 'Idempotency-Key': 'changed-resubmit'})
    assert replacement.status_code == 200
    assert replacement.json()['action_hash'] != submitted['action_hash']
    assert client.post(base + '/start', headers={**auth_headers, 'Idempotency-Key': 'premature-new-start'}).status_code == 403
    assert client.post('/api/v1/approvals/' + replacement.json()['approval_id'] + '/approve', json={'reason': 'Approved replacement'}, headers={**auth_headers, 'Idempotency-Key': 'replacement-approve'}).status_code == 200
    assert client.post(base + '/start', headers={**auth_headers, 'Idempotency-Key': 'replacement-start'}).json()['status'] == 'QUEUED'


def test_rejected_or_disabled_policy_never_authorizes_execution(client, auth_headers):
    from datetime import UTC, datetime, timedelta
    from uuid import UUID
    from app.db.models import Policy
    from app.db.session import get_db
    from app.main import app

    opp = client.post('/api/v1/opportunities', json={'title': 'Reject test', 'business_model': 'AI_SERVICES'}, headers={**auth_headers, 'Idempotency-Key': 'reject-opp'}).json()
    workflow = client.post('/api/v1/workflows', json={'opportunity_id': opp['id'], 'name': 'Reject workflow'}, headers={**auth_headers, 'Idempotency-Key': 'reject-workflow'}).json()
    base = '/api/v1/workflows/' + workflow['id']
    assert client.post(base + '/tasks', json={'name': 'Validate', 'task_type': 'VALIDATE_OPPORTUNITY', 'assigned_role': 'research'}, headers={**auth_headers, 'Idempotency-Key': 'reject-task'}).status_code == 201
    policy_id = client.get('/api/v1/policies', headers=auth_headers).json()[0]['id']
    submit = {'policy_id': policy_id, 'expires_at': (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    db.get(Policy, UUID(policy_id)).enabled = False
    db.commit(); generator.close()
    assert client.post(base + '/submit', json=submit, headers={**auth_headers, 'Idempotency-Key': 'disabled-policy'}).status_code == 403
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    db.get(Policy, UUID(policy_id)).enabled = True
    db.commit(); generator.close()
    submitted = client.post(base + '/submit', json=submit, headers={**auth_headers, 'Idempotency-Key': 'reject-submit'}).json()
    rejected = client.post('/api/v1/approvals/' + submitted['approval_id'] + '/reject', json={'reason': 'Owner declined'}, headers={**auth_headers, 'Idempotency-Key': 'reject-decision'})
    assert rejected.status_code == 200
    assert client.post(base + '/start', headers={**auth_headers, 'Idempotency-Key': 'reject-start'}).status_code == 403
    assert client.post(base + '/reopen', headers={**auth_headers, 'Idempotency-Key': 'reject-reopen'}).json()['status'] == 'DRAFT'
    task = client.get(base + '/tasks', headers=auth_headers).json()[0]
    forged = {'policy_id': policy_id, 'approval_id': submitted['approval_id'], 'cost_usd': '10'}
    assert client.post(base + '/tasks/' + task['id'] + '/queue', json=forged, headers={**auth_headers, 'Idempotency-Key': 'forged-cost'}).status_code == 422
