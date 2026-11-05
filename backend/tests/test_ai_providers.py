from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select

from app.ai_brain.credentials import CredentialUnavailable, decrypt_credential, encrypt_credential
from app.core.config import get_settings
from app.db.models import Agent, AIProvider, AuditEvent, IdempotencyRecord
from app.db.session import get_db
from app.main import app


@pytest.fixture
def encryption_key(monkeypatch):
    monkeypatch.setattr(get_settings(), 'ai_credentials_key', SecretStr(Fernet.generate_key().decode()))


def test_encryption_is_authenticated_and_bound_to_provider(encryption_key):
    provider_id = uuid4()
    encrypted = encrypt_credential(provider_id, 'test-secret-value')
    assert 'test-secret-value' not in encrypted
    assert decrypt_credential(provider_id, encrypted) == 'test-secret-value'
    with pytest.raises(CredentialUnavailable):
        decrypt_credential(uuid4(), encrypted)
    with pytest.raises(CredentialUnavailable):
        decrypt_credential(provider_id, encrypted[:-4] + 'AAAA')


def test_owner_provider_create_is_disabled_redacted_and_idempotent(client, auth_headers, encryption_key):
    data = {'name': 'Test provider', 'kind': 'OPENAI', 'default_model': 'owner-model', 'api_key': 'test-secret-value'}
    headers = auth_headers | {'Idempotency-Key': 'provider-create-1'}
    assert client.get('/api/v1/ai/providers').status_code == 401
    response = client.post('/api/v1/ai/providers', json=data, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()['enabled'] is False and response.json()['has_api_key'] is True
    assert 'test-secret-value' not in response.text and 'encrypted_api_key' not in response.text
    session_generator = app.dependency_overrides[get_db]()
    db = next(session_generator)
    stored = db.scalar(select(AIProvider))
    assert stored.encrypted_api_key != 'test-secret-value'
    assert decrypt_credential(stored.id, stored.encrypted_api_key) == 'test-secret-value'
    assert 'test-secret-value' not in repr(db.scalar(select(IdempotencyRecord)).__dict__)
    assert 'test-secret-value' not in repr(db.scalar(select(AuditEvent)).detail)
    session_generator.close()
    assert client.post('/api/v1/ai/providers', json=data, headers=headers).json() == response.json()
    changed = dict(data, api_key='another-secret')
    assert client.post('/api/v1/ai/providers', json=changed, headers=headers).status_code == 409
    listed = client.get('/api/v1/ai/providers', headers=auth_headers)
    assert listed.status_code == 200 and 'test-secret-value' not in listed.text
    provider_id = response.json()['id']
    default_headers = auth_headers | {'Idempotency-Key': 'provider-default'}
    default = client.post(f'/api/v1/ai/providers/{provider_id}/default', headers=default_headers)
    assert default.status_code == 200 and default.json()['is_default'] is True
    assert client.post(f'/api/v1/ai/providers/{provider_id}/default', headers=default_headers).json() == default.json()
    update_headers = auth_headers | {'Idempotency-Key': 'provider-update-1'}
    update = client.patch(f'/api/v1/ai/providers/{provider_id}', headers=update_headers,
                          json={'api_key': 'new-test-secret', 'default_model': 'another-model', 'enabled': True})
    assert update.status_code == 200 and update.json()['enabled'] is True
    assert 'new-test-secret' not in update.text
    assert client.patch(f'/api/v1/ai/providers/{provider_id}', headers=update_headers,
                        json={'api_key': 'new-test-secret', 'default_model': 'another-model', 'enabled': True}).json() == update.json()
    revoked = client.patch(f'/api/v1/ai/providers/{provider_id}', headers=auth_headers | {'Idempotency-Key': 'provider-revoke'}, json={'revoke_api_key': True})
    assert revoked.status_code == 200 and not revoked.json()['has_api_key'] and not revoked.json()['enabled']
    archived = client.post(f'/api/v1/ai/providers/{provider_id}/archive', headers=auth_headers | {'Idempotency-Key': 'provider-archive'})
    assert archived.status_code == 200 and archived.json()['archived'] and not archived.json()['is_default']
    assert client.get('/api/v1/ai/providers', headers=auth_headers).json() == []


def test_missing_encryption_key_fails_closed(client, auth_headers, monkeypatch):
    monkeypatch.setattr(get_settings(), 'ai_credentials_key', None)
    result = client.post('/api/v1/ai/providers', headers=auth_headers | {'Idempotency-Key': 'provider-no-key'},
                         json={'name': 'Test', 'kind': 'OPENAI', 'default_model': 'model', 'api_key': 'do-not-log'})
    assert result.status_code == 503 and 'do-not-log' not in result.text
    assert client.get('/api/v1/ai/providers', headers=auth_headers).json() == []


def test_provider_rejects_url_credentials(client, auth_headers):
    result = client.post('/api/v1/ai/providers', headers=auth_headers | {'Idempotency-Key': 'invalid-url'},
                         json={'name': 'Test', 'kind': 'OPENAI_COMPATIBLE', 'default_model': 'model', 'base_url': 'https://user:pass@example.com'})
    assert result.status_code == 422


def test_agent_profile_owner_validation_and_idempotency(client, auth_headers):
    provider_response = client.post('/api/v1/ai/providers', headers=auth_headers | {'Idempotency-Key': 'profile-provider'},
                                    json={'name': 'For research', 'kind': 'OPENAI', 'default_model': 'base-model'})
    assert provider_response.status_code == 201
    session_generator = app.dependency_overrides[get_db]()
    db = next(session_generator)
    agent_id = str(db.scalar(select(Agent)).id)
    session_generator.close()
    path = f'/api/v1/ai/agent-profiles/{agent_id}'
    payload = {'provider_id': provider_response.json()['id'], 'model_id': 'research-model', 'max_output_tokens': 1200,
               'temperature': '0.5', 'timeout_seconds': 60, 'max_cost_usd': '1.5', 'enabled': False}
    assert client.put(path, json=payload, headers={'Idempotency-Key': 'anonymous'}).status_code == 401
    headers = auth_headers | {'Idempotency-Key': 'configure-research'}
    first = client.put(path, json=payload, headers=headers)
    assert first.status_code == 200 and first.json()['model_id'] == 'research-model'
    assert client.put(path, json=payload, headers=headers).json() == first.json()
    assert client.put(path, json=dict(payload, max_cost_usd='46'), headers=auth_headers | {'Idempotency-Key': 'too-expensive'}).status_code == 422
    assert client.put(path, json=dict(payload, model_id='different'), headers=headers).status_code == 409
    assert len(client.get('/api/v1/ai/agent-profiles', headers=auth_headers).json()) == 1


def test_pricing_versions_are_immutable_audited_and_decimal(client, auth_headers):
    provider = client.post('/api/v1/ai/providers', headers=auth_headers | {'Idempotency-Key': 'price-provider'},
                           json={'name': 'Pricing provider', 'kind': 'OPENAI', 'default_model': 'owner-model'}).json()
    path = f"/api/v1/ai/providers/{provider['id']}/prices"
    price = {'model_id': 'owner-model', 'version': '2026-11', 'input_per_million': '0.500000',
             'output_per_million': '1.250000', 'effective_at': '2026-11-01T00:00:00Z', 'source_note': 'Owner reviewed provider price'}
    headers = auth_headers | {'Idempotency-Key': 'price-version-1'}
    assert client.get(path).status_code == 401
    created = client.post(path, headers=headers, json=price)
    assert created.status_code == 201 and created.json()['input_per_million'] == '0.500000'
    assert client.post(path, headers=headers, json=price).json() == created.json()
    assert client.post(path, headers=auth_headers | {'Idempotency-Key': 'duplicate-version'}, json=price).status_code == 409
    assert client.post(path, headers=auth_headers | {'Idempotency-Key': 'bad-period'}, json=dict(price, version='v2', effective_at='2026-11-01T00:00:00')).status_code == 422
    assert client.post(path, headers=auth_headers | {'Idempotency-Key': 'float-cost'}, json=dict(price, version='v3', input_per_million=0.1)).status_code == 422
    assert len(client.get(path, headers=auth_headers).json()) == 1
    quote = client.post(f"{path}/{created.json()['id']}/quote", headers=auth_headers, json={'max_input_tokens': 1000, 'max_output_tokens': 500, 'attempts': 2})
    assert quote.status_code == 200 and quote.json()['estimated_ceiling_usd'] == '0.002250'
    assert 'No approval or reservation' in quote.json()['disclaimer']
