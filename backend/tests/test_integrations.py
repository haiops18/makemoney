"""Owner integrations: secrets are write-only, settings are validated, checks hit one fixed host."""
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select

from app.api import integration_routes
from app.ai_brain.network import NetworkDenied, provider_request
from app.core.config import get_settings
from app.db.models import AuditEvent, Integration
from app.db.session import get_db
from app.main import app

TOKEN = 'EAAG-page-token-secret-123'


@pytest.fixture(autouse=True)
def credential_key(monkeypatch):
    monkeypatch.setattr(get_settings(), 'ai_credentials_key', SecretStr(Fernet.generate_key().decode()))


def send(client, headers, method, path, body=None, key=None):
    return client.request(method, '/api/v1/integrations' + path, json=body, headers={**headers, 'Idempotency-Key': key or str(uuid4())})


def facebook(client, headers, **extra):
    body = {'kind': 'FACEBOOK_PAGE', 'label': 'Trang váy hè', 'config': {'page_id': '1234567890'}, 'secret': TOKEN, **extra}
    return send(client, headers, 'POST', '', body)


def test_requires_owner_and_never_returns_the_secret(client, auth_headers):
    assert client.get('/api/v1/integrations').status_code == 401
    created = facebook(client, auth_headers)
    assert created.status_code == 201, created.text
    data = created.json()
    assert data['has_secret'] is True and data['config'] == {'page_id': '1234567890', 'graph_version': 'v26.0'} and data['purpose'] == 'posting'
    listed = client.get('/api/v1/integrations', headers=auth_headers)
    assert TOKEN not in created.text and TOKEN not in listed.text
    db = next(app.dependency_overrides[get_db]())
    stored = db.scalar(select(Integration))
    assert stored.encrypted_secret and TOKEN not in stored.encrypted_secret
    audit = db.scalar(select(AuditEvent).where(AuditEvent.action == 'integration.created'))
    assert TOKEN not in str(audit.detail)


def test_settings_and_tokens_are_validated(client, auth_headers):
    assert facebook(client, auth_headers, config={'page_id': 'abc'}).status_code == 422
    assert facebook(client, auth_headers, config={'page_id': '1234567890', 'graph_version': 'latest'}).status_code == 422
    assert facebook(client, auth_headers, config={'page_id': '1234567890', 'url': 'x'}).status_code == 422
    assert facebook(client, auth_headers, secret='has space').status_code == 422
    assert send(client, auth_headers, 'POST', '', {'kind': 'ACCESSTRADE', 'label': 'AT', 'config': {'host': 'evil'}, 'secret': 'k'}).status_code == 422
    assert send(client, auth_headers, 'POST', '', {'kind': 'SHOPEE', 'label': 'x', 'secret': 'k'}).status_code == 422
    assert facebook(client, auth_headers).status_code == 201
    assert facebook(client, auth_headers).status_code == 409  # same kind and name


def test_create_is_idempotent_and_update_resets_the_check(client, auth_headers):
    body = {'kind': 'ACCESSTRADE', 'label': 'ACCESSTRADE', 'secret': 'at-key'}
    key = str(uuid4())
    first = send(client, auth_headers, 'POST', '', body, key)
    assert send(client, auth_headers, 'POST', '', body, key).json() == first.json()
    assert send(client, auth_headers, 'POST', '', {**body, 'secret': 'other'}, key).status_code == 409
    item = first.json()
    db = next(app.dependency_overrides[get_db]())
    row = db.get(Integration, __import__('uuid').UUID(item['id']))
    row.last_check_status = 'OK'
    db.commit()
    updated = send(client, auth_headers, 'PATCH', f"/{item['id']}", {'secret': 'new-key', 'label': 'AT chính'})
    assert updated.status_code == 200 and updated.json()['label'] == 'AT chính' and updated.json()['last_check_status'] is None
    archived = send(client, auth_headers, 'POST', f"/{item['id']}/archive")
    assert archived.status_code == 200 and archived.json()['has_secret'] is False
    assert client.get('/api/v1/integrations', headers=auth_headers).json() == []
    assert send(client, auth_headers, 'POST', f"/{item['id']}/test").status_code == 404


def test_connection_check_uses_the_fixed_host_and_records_the_outcome(client, auth_headers, monkeypatch):
    calls = []

    def fake(method, url, hosts, headers, payload, timeout, query=None):
        calls.append((method, url, hosts, headers, payload, query))
        return 200, {'id': '1234567890', 'name': 'Váy hè xinh'}
    monkeypatch.setattr(integration_routes, 'connection_transport', fake)
    item = facebook(client, auth_headers).json()
    checked = send(client, auth_headers, 'POST', f"/{item['id']}/test")
    assert checked.status_code == 200 and checked.json()['last_check_status'] == 'OK' and checked.json()['last_check_detail'] == 'Page: Váy hè xinh'
    assert calls == [('GET', 'https://graph.facebook.com/v26.0/1234567890', {'graph.facebook.com'}, {'Authorization': f'Bearer {TOKEN}'}, None, {'fields': 'id,name'})]
    assert TOKEN not in checked.text

    monkeypatch.setattr(integration_routes, 'connection_transport', lambda *a, **k: (401, {'error': {'message': TOKEN}}))
    failed = send(client, auth_headers, 'POST', f"/{item['id']}/test")
    assert failed.json()['last_check_status'] == 'AUTH_FAILED' and TOKEN not in failed.text
    monkeypatch.setattr(integration_routes, 'connection_transport', lambda *a, **k: (200, {'id': '999', 'name': 'Other page'}))
    assert send(client, auth_headers, 'POST', f"/{item['id']}/test").json()['last_check_status'] == 'INVALID_RESPONSE'

    def boom(*a, **k):
        raise NetworkDenied('x')
    monkeypatch.setattr(integration_routes, 'connection_transport', boom)
    assert send(client, auth_headers, 'POST', f"/{item['id']}/test").json()['last_check_status'] == 'UNREACHABLE'


@pytest.mark.parametrize('kind,response,detail', [
    ('SEARCH_TAVILY', {'results': [{'url': 'https://a'}]}, '1 result(s)'),
    ('SEARCH_BRAVE', {'web': {'results': [{}, {}]}}, '2 result(s)'),
    ('ACCESSTRADE', {'data': [{'id': '1'}], 'total': 12}, '12 approved campaign(s)'),
])
def test_every_kind_checks_its_own_official_host(client, auth_headers, monkeypatch, kind, response, detail):
    seen = {}

    def fake(method, url, hosts, headers, payload, timeout, query=None):
        seen.update(url=url, hosts=hosts, headers=headers)
        return 200, response
    monkeypatch.setattr(integration_routes, 'connection_transport', fake)
    item = send(client, auth_headers, 'POST', '', {'kind': kind, 'label': kind, 'secret': 'tok-1'}).json()
    checked = send(client, auth_headers, 'POST', f"/{item['id']}/test").json()
    assert checked['last_check_status'] == 'OK' and checked['last_check_detail'] == detail
    assert len(seen['hosts']) == 1 and seen['url'].startswith('https://' + next(iter(seen['hosts'])) + '/')
    assert 'tok-1' in ' '.join(seen['headers'].values())
    assert checked['check_costs'] is kind.startswith('SEARCH')


def test_transport_rejects_bad_queries_and_headers():
    with pytest.raises(NetworkDenied):
        provider_request('GET', 'https://api.accesstrade.vn/v1/campaigns', {'api.accesstrade.vn'}, {}, None, 5, query={'q': 'x' * 501})
    with pytest.raises(NetworkDenied):
        provider_request('GET', 'https://api.accesstrade.vn/v1/campaigns', {'api.accesstrade.vn'}, {'Cookie': 'a'}, None, 5)
    with pytest.raises(NetworkDenied):
        provider_request('GET', 'https://evil.example/v1', {'api.accesstrade.vn'}, {}, None, 5)
