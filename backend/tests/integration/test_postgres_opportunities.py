import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Opportunity, OpportunityEvidence


@pytest.mark.postgres
def test_concurrent_api_retry_is_one_audited_mutation():
    url = os.getenv('POSTGRES_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Isolated PostgreSQL required')
    from uuid import uuid4
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import get_db
    from app.db.models import AuditEvent
    from sqlalchemy import func
    engine = create_engine(url)
    def database():
        with Session(engine, expire_on_commit=False) as session:
            yield session
    app.dependency_overrides[get_db] = database
    key = str(uuid4())
    try:
        def create(_):
            with TestClient(app) as client:
                result = client.post('/api/v1/opportunities', json={'title': 'Concurrent API', 'business_model': 'MICRO_SAAS'}, headers={'Authorization': 'Bearer test-owner-key', 'Idempotency-Key': key})
                assert result.status_code == 201, result.text
                return result.json()['id']
        with ThreadPoolExecutor(max_workers=4) as executor:
            ids = list(executor.map(create, range(4)))
        assert len(set(ids)) == 1
        with Session(engine) as session:
            from uuid import UUID
            assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == UUID(ids[0]), AuditEvent.action == 'opportunity.created')) == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.postgres
def test_opportunity_constraints_rollback_and_row_lock():
    url = os.getenv('POSTGRES_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Isolated PostgreSQL required')
    engine = create_engine(url)
    with Session(engine) as session:
        assert session.scalar(text('SELECT version_num FROM alembic_version')) == '20261102_0004'
        record = Opportunity(title='Isolated concurrency test', business_model='NEW_EXTENSIBLE_MODEL', created_by='test')
        session.add(record)
        session.commit()
        opportunity_id = record.id
        record.score = 101
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.get(Opportunity, opportunity_id).score is None
    def increment(_):
        with Session(engine) as session:
            record = session.scalar(select(Opportunity).where(Opportunity.id == opportunity_id).with_for_update())
            record.time_to_validate_days = (record.time_to_validate_days or 0) + 1
            session.commit()
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(increment, range(4)))
    with Session(engine) as session:
        assert session.get(Opportunity, opportunity_id).time_to_validate_days == 4
        session.add(OpportunityEvidence(opportunity_id='00000000-0000-0000-0000-000000000001', source_name='test', source_type='test', evidence_type='test', summary='test', captured_at=__import__('datetime').datetime.now(__import__('datetime').UTC)))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
