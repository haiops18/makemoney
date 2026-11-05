import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.main import app
from app.orchestration.worker import activate_one, run_once


@pytest.mark.postgres
def test_research_workflow_validates_draft_only_after_separate_approvals():
    url = os.getenv('POSTGRES_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Isolated PostgreSQL required')
    engine = create_engine(url)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    def database():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = database
    headers = {'Authorization': 'Bearer test-owner-key'}
    def key(): return headers | {'Idempotency-Key': str(uuid4())}
    expiry = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    try:
        with TestClient(app) as client:
            draft = client.post('/api/v1/ai/research', json={'objective': 'Owner research', 'target_market': 'VN', 'max_cost_usd': '1'}, headers=key())
            assert draft.status_code == 201
            run_id = draft.json()['id']
            assert client.post(f'/api/v1/ai/research/{run_id}/sources', json={'source_name': 'Owner source', 'excerpt': 'Unverified claim'}, headers=key()).status_code == 201
            created = client.post(f'/api/v1/ai/research/{run_id}/workflow', json={'name': 'Research validation'}, headers=key())
            assert created.status_code == 201, created.text
            workflow_id = created.json()['id']
            base = f'/api/v1/workflows/{workflow_id}'
            task = client.get(base + '/tasks', headers=headers).json()[0]
            policy_id = next(item['id'] for item in client.get('/api/v1/policies', headers=headers).json() if 'INTERNAL_WORKFLOW' in item['rules_json']['allowed_action_types'])
            submitted = client.post(base + '/submit', json={'policy_id': policy_id, 'expires_at': expiry}, headers=key())
            assert submitted.status_code == 200, submitted.text
            assert client.post(base + '/start', headers=key()).status_code == 403
            approval_id = submitted.json()['approval_id']
            assert client.post(f'/api/v1/approvals/{approval_id}/approve', json={'reason': 'Owner reviewed workflow'}, headers=key()).status_code == 200
            assert client.post(base + '/start', headers=key()).status_code == 200
            for _ in range(100):
                if client.get(base, headers=headers).json()['status'] == 'RUNNING':
                    break
                assert activate_one(factory)
            assert client.get(base, headers=headers).json()['status'] == 'RUNNING'
            prepared = client.get(f"{base}/tasks/{task['id']}/approval-action", params={'policy_id': policy_id}, headers=headers).json()['action']
            body = {name: prepared[name] for name in ('policy_id', 'action_type', 'action_payload', 'resource_type', 'resource_id', 'scope')}
            body['expires_at'] = expiry
            approval = client.post('/api/v1/approvals', json=body, headers=key())
            assert approval.status_code == 201, approval.text
            assert client.post(f"/api/v1/approvals/{approval.json()['id']}/approve", json={'reason': 'Owner reviewed validation task'}, headers=key()).status_code == 200
            queued = client.post(f"{base}/tasks/{task['id']}/queue", json={'policy_id': policy_id, 'approval_id': approval.json()['id']}, headers=key())
            assert queued.status_code == 201, queued.text
            for _ in range(100):
                if client.get(base + '/tasks', headers=headers).json()[0]['status'] == 'SUCCEEDED':
                    break
                assert run_once(factory)
            assert client.get(base + '/tasks', headers=headers).json()[0]['status'] == 'SUCCEEDED'
            assert client.get(base, headers=headers).json()['status'] == 'COMPLETED'
            assert client.get(f'/api/v1/ai/research/{run_id}/sources', headers=headers).json()[0]['verification_status'] == 'UNVERIFIED'
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
