import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AIProvider, AuditEvent
from app.db.session import get_db
from app.main import app


@pytest.mark.postgres
def test_concurrent_provider_creation_is_single_encrypted_mutation(monkeypatch):
    url = os.getenv('POSTGRES_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Isolated PostgreSQL required')
    monkeypatch.setattr(get_settings(), 'ai_credentials_key', SecretStr(Fernet.generate_key().decode()))
    engine = create_engine(url)
    def database():
        with Session(engine, expire_on_commit=False) as session:
            yield session
    app.dependency_overrides[get_db] = database
    key = str(uuid4())
    data = {'name': f'Provider {key}', 'kind': 'OPENAI', 'default_model': 'model', 'api_key': 'isolated-test-credential'}
    try:
        def create(_):
            with TestClient(app) as client:
                response = client.post('/api/v1/ai/providers', json=data, headers={'Authorization': 'Bearer test-owner-key', 'Idempotency-Key': key})
                assert response.status_code == 201, response.text
                assert 'isolated-test-credential' not in response.text
                return response.json()['id']
        with ThreadPoolExecutor(max_workers=4) as executor:
            ids = list(executor.map(create, range(4)))
        assert len(set(ids)) == 1
        with Session(engine) as db:
            provider = db.get(AIProvider, UUID(ids[0]))
            assert provider.encrypted_api_key != 'isolated-test-credential'
            assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == provider.id, AuditEvent.action == 'ai_provider.created')) == 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.postgres
def test_concurrent_default_selection_has_only_one_default():
    url = os.getenv('POSTGRES_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Isolated PostgreSQL required')
    engine = create_engine(url)
    with Session(engine, expire_on_commit=False) as db:
        first = AIProvider(name=f'First {uuid4()}', kind='OPENAI', default_model='test')
        second = AIProvider(name=f'Second {uuid4()}', kind='GEMINI', default_model='test')
        db.add_all([first, second])
        db.commit()
        ids = [first.id, second.id]
    def database():
        with Session(engine, expire_on_commit=False) as session:
            yield session
    app.dependency_overrides[get_db] = database
    try:
        def choose(provider_id):
            with TestClient(app) as client:
                result = client.post(f'/api/v1/ai/providers/{provider_id}/default',
                                     headers={'Authorization': 'Bearer test-owner-key', 'Idempotency-Key': str(uuid4())})
                assert result.status_code == 200, result.text
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(choose, ids))
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(AIProvider).where(AIProvider.is_default.is_(True))) == 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
