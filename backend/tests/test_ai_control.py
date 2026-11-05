from datetime import UTC, datetime, timedelta

from app.db.models import AIExecutionControl, Policy
from app.db.session import get_db
from app.main import app


def seed_control():
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    control = AIExecutionControl(name='primary', enabled=False, version=1)
    policy = Policy(name='test-ai-control', version='1', description='Owner-controlled test', enabled=True,
                    rules_json={'allowed_action_types': ['AI_CONTROL_ENABLE', 'AI_INFERENCE'], 'authorization_scope': 'ONCE',
                                'require_approval': True, 'external_execution': False, 'ai_inference_allowed': True})
    db.add_all([control, policy])
    db.commit()
    result = str(control.id), str(policy.id)
    generator.close()
    return result


def prepare_approval(client, headers, policy_id, suffix):
    prepared = client.get('/api/v1/ai/control/enable-action', params={'policy_id': policy_id}, headers=headers)
    assert prepared.status_code == 200
    action = prepared.json()['action']
    request = {'policy_id': action['policy_id'], 'action_type': action['action_type'], 'action_payload': action['action_payload'],
               'resource_type': action['resource_type'], 'resource_id': action['resource_id'], 'scope': action['scope'],
               'expires_at': (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}
    approval = client.post('/api/v1/approvals', json=request, headers=headers | {'Idempotency-Key': f'request-{suffix}'})
    assert approval.status_code == 201
    result = client.post(f"/api/v1/approvals/{approval.json()['id']}/approve", json={'reason': 'Owner reviewed AI consent'}, headers=headers | {'Idempotency-Key': f'approve-{suffix}'})
    assert result.status_code == 200
    return approval.json()['id']


def test_ai_control_requires_exact_one_time_owner_approval(client, auth_headers):
    _, policy_id = seed_control()
    assert client.get('/api/v1/ai/control').status_code == 401
    initial = client.get('/api/v1/ai/control', headers=auth_headers)
    assert initial.json()['enabled'] is False and initial.json()['execution_available'] is False
    approval_id = prepare_approval(client, auth_headers, policy_id, 'first')
    body = {'policy_id': policy_id, 'approval_id': approval_id}
    headers = auth_headers | {'Idempotency-Key': 'enable-first'}
    enabled = client.post('/api/v1/ai/control/enable', json=body, headers=headers)
    assert enabled.status_code == 200 and enabled.json()['enabled'] is True and enabled.json()['execution_available'] is False
    assert client.post('/api/v1/ai/control/enable', json=body, headers=headers).json() == enabled.json()
    disabled = client.post('/api/v1/ai/control/disable', headers=auth_headers | {'Idempotency-Key': 'disable-first'})
    assert disabled.status_code == 200 and disabled.json()['enabled'] is False
    replay = client.post('/api/v1/ai/control/enable', json=body, headers=auth_headers | {'Idempotency-Key': 'replay-old'})
    assert replay.status_code == 403


def test_disabling_invalidates_prepared_approval_and_wrong_policy_denies(client, auth_headers):
    _, policy_id = seed_control()
    original = client.get('/api/v1/policies', headers=auth_headers).json()
    internal_id = next(item['id'] for item in original if item['name'] == 'owner-controlled-internal')
    assert client.get('/api/v1/ai/control/enable-action', params={'policy_id': internal_id}, headers=auth_headers).status_code == 403
    approval_id = prepare_approval(client, auth_headers, policy_id, 'stale')
    assert client.post('/api/v1/ai/control/disable', headers=auth_headers | {'Idempotency-Key': 'disable-before-enable'}).status_code == 200
    stale = client.post('/api/v1/ai/control/enable', json={'policy_id': policy_id, 'approval_id': approval_id}, headers=auth_headers | {'Idempotency-Key': 'enable-stale'})
    assert stale.status_code == 403
    assert client.get('/api/v1/ai/control', headers=auth_headers).json()['enabled'] is False
