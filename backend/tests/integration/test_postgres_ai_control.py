import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import AIExecutionControl, AuditEvent
from app.db.session import get_db
from app.main import app


@pytest.mark.postgres
def test_concurrent_ai_consent_consumes_one_approval():
    url = os.getenv('POSTGRES_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Isolated PostgreSQL required')
    engine = create_engine(url)
    def database():
        with Session(engine, autoflush=False, expire_on_commit=False) as db:
            yield db
    app.dependency_overrides[get_db] = database
    headers = {'Authorization': 'Bearer test-owner-key'}
    def key():
        return headers | {'Idempotency-Key': str(uuid4())}
    try:
        with TestClient(app) as client:
            if client.get('/api/v1/ai/control', headers=headers).json()['enabled']:
                assert client.post('/api/v1/ai/control/disable', headers=key()).status_code == 200
            policy_id = next(item['id'] for item in client.get('/api/v1/policies', headers=headers).json() if item['name'] == 'ai-inference-controlled')
            action = client.get('/api/v1/ai/control/enable-action', params={'policy_id': policy_id}, headers=headers).json()['action']
            body = {name: action[name] for name in ('policy_id', 'action_type', 'action_payload', 'resource_type', 'resource_id', 'scope')}
            body['expires_at'] = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
            approval = client.post('/api/v1/approvals', json=body, headers=key())
            assert approval.status_code == 201, approval.text
            approval_id = approval.json()['id']
            assert client.post(f'/api/v1/approvals/{approval_id}/approve', json={'reason': 'Owner reviewed test action'}, headers=key()).status_code == 200
        def enable(_):
            with TestClient(app) as client:
                response = client.post('/api/v1/ai/control/enable', json={'policy_id': policy_id, 'approval_id': approval_id}, headers=key())
                return response.status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(enable, range(2)))
        assert sorted(results) == [200, 409]
        with Session(engine) as db:
            control = db.scalar(select(AIExecutionControl).where(AIExecutionControl.name == 'primary'))
            assert control.enabled is True
            assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == control.id, AuditEvent.action == 'ai_control.enabled')) >= 1
        with TestClient(app) as client:
            state = client.get('/api/v1/ai/control', headers=headers).json()
            assert state['execution_available'] is False
            assert client.post('/api/v1/ai/control/disable', headers=key()).status_code == 200
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
