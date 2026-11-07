"""Step 7A campaign constraints on the real migrated PostgreSQL schema."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AffiliateProgramTerm, AuditEvent, Campaign, CampaignProduct
from app.db.session import get_db
from app.main import app

SCORES = {key: 80 for key in ['market_demand', 'monetization_potential', 'automation_feasibility', 'experiment_cost', 'competitive_advantage', 'scalability', 'evidence_confidence']}
HEADERS = {'Authorization': 'Bearer test-owner-key'}


def key():
    return HEADERS | {'Idempotency-Key': str(uuid4())}


@pytest.fixture()
def pg():
    url = os.getenv('POSTGRES_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Isolated PostgreSQL required')
    engine = create_engine(url)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def database():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = database
    try:
        yield engine
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _campaign(client) -> str:
    opportunity = client.post('/api/v1/opportunities', json={'title': f'Affiliate {uuid4()}', 'business_model': 'AFFILIATE'}, headers=key()).json()
    assert client.post(f"/api/v1/opportunities/{opportunity['id']}/evaluate", json={'scores': SCORES, 'risk_level': 'LOW'}, headers=key()).status_code == 200
    created = client.post('/api/v1/campaigns', json={'opportunity_id': opportunity['id'], 'name': 'PG campaign', 'max_cost_usd': '2'}, headers=key())
    assert created.status_code == 201, created.text
    return created.json()['id']


def _source(client, campaign_id: str) -> str:
    return client.post(f'/api/v1/campaigns/{campaign_id}/sources', json={'source_name': 'S', 'excerpt': 'E', 'captured_at': datetime.now(UTC).isoformat()}, headers=key()).json()['id']


@pytest.mark.postgres
def test_concurrent_campaign_retry_creates_one_audited_campaign(pg):
    with TestClient(app) as client:
        opportunity = client.post('/api/v1/opportunities', json={'title': f'Race {uuid4()}', 'business_model': 'AFFILIATE'}, headers=key()).json()
        assert client.post(f"/api/v1/opportunities/{opportunity['id']}/evaluate", json={'scores': SCORES, 'risk_level': 'LOW'}, headers=key()).status_code == 200
    headers = key()
    body = {'opportunity_id': opportunity['id'], 'name': 'Race', 'max_cost_usd': '1'}

    def create(_):
        with TestClient(app) as client:
            result = client.post('/api/v1/campaigns', json=body, headers=headers)
            assert result.status_code == 201, result.text
            return result.json()['id']
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = set(pool.map(create, range(4)))
    assert len(ids) == 1
    with Session(pg) as db:
        assert db.scalar(select(func.count()).select_from(Campaign).where(Campaign.opportunity_id == opportunity['id'])) == 1
        from uuid import UUID
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'campaign.created', AuditEvent.entity_id == UUID(ids.pop()))) == 1


@pytest.mark.postgres
def test_database_rejects_cross_campaign_evidence_and_unsourced_prices(pg):
    with TestClient(app) as client:
        first, second = _campaign(client), _campaign(client)
        foreign_source = _source(client, second)
        program = client.post(f'/api/v1/campaigns/{first}/programs', json={'network': 'SHOPEE', 'name': 'Shopee', 'link_hosts': ['shopee.vn']}, headers=key()).json()
    with Session(pg) as db:
        db.add(AffiliateProgramTerm(campaign_id=first, program_id=program['id'], term='PAYOUT', value_text='x', unit='NONE', source_id=foreign_source, created_by='owner'))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(CampaignProduct(campaign_id=first, name='Váy', price_text='199.000đ', created_by='owner'))
        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.postgres
def test_only_one_active_link_per_final_url(pg):
    with TestClient(app) as client:
        campaign_id = _campaign(client)
        program = client.post(f'/api/v1/campaigns/{campaign_id}/programs', json={'network': 'SHOPEE', 'name': 'Shopee', 'link_hosts': ['shopee.vn'], 'tracking_param_keys': ['sub_id']}, headers=key()).json()
        link = {'program_id': program['id'], 'label': 'L', 'original_url': 'https://shopee.vn/p', 'tracking_params': {'sub_id': 'a'}}
        created = client.post(f'/api/v1/campaigns/{campaign_id}/links', json=link, headers=key())
        assert created.status_code == 201, created.text
        assert client.post(f'/api/v1/campaigns/{campaign_id}/links', json=link, headers=key()).status_code == 409
        assert client.post(f"/api/v1/campaigns/{campaign_id}/links/{created.json()['id']}/retire", headers=key()).status_code == 200
        assert client.post(f'/api/v1/campaigns/{campaign_id}/links', json=link, headers=key()).status_code == 201
