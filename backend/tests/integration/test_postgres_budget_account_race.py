import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, BudgetAccount, BudgetReservation
from app.finance import service
from app.db.session import get_db
from app.main import app
from fastapi.testclient import TestClient


@pytest.mark.postgres
def test_first_month_account_race_preserves_both_outer_transactions(monkeypatch):
    url = os.getenv('POSTGRES_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Isolated PostgreSQL required')
    engine = create_engine(url)
    account_name = f'isolation-test-{uuid4()}'
    monkeypatch.setattr(service, 'MONTHLY_ACCOUNT_NAME', account_name)
    barrier = Barrier(2, timeout=10)
    audit_ids = [uuid4(), uuid4()]

    def create(index):
        with Session(engine, autoflush=False) as db:
            db.add(AuditEvent(id=audit_ids[index], actor='owner', action='test.month_race', entity_type='test', entity_id=uuid4(), detail={}))
            db.flush()
            original = db.scalar
            first = True
            def synchronize_initial_read(*args, **kwargs):
                nonlocal first
                result = original(*args, **kwargs)
                if first:
                    first = False
                    barrier.wait()
                return result
            db.scalar = synchronize_initial_read
            account_id = service.current_account(db, lock=True).id
            db.commit()
            return account_id

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            ids = list(executor.map(create, range(2)))
        assert len(set(ids)) == 1
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(BudgetAccount).where(BudgetAccount.name == account_name)) == 1
            assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.id.in_(audit_ids))) == 2
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_postgres_records_verified_overage_and_enforces_hard_stop(monkeypatch):
    url = os.getenv('POSTGRES_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Isolated PostgreSQL required')
    engine = create_engine(url)
    monkeypatch.setattr(service, 'MONTHLY_ACCOUNT_NAME', f'overage-test-{uuid4()}')
    def database():
        with Session(engine, autoflush=False, expire_on_commit=False) as session:
            yield session
    app.dependency_overrides[get_db] = database
    headers = {'Authorization': 'Bearer test-owner-key'}
    try:
        with TestClient(app) as client:
            body = {'task_id': str(uuid4()), 'reserved_amount': '2', 'currency': 'USD', 'expires_at': (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}
            reservation = client.post('/api/v1/budgets/reservations', json=body, headers=headers | {'Idempotency-Key': str(uuid4())})
            assert reservation.status_code == 201, reservation.text
            settled = client.post(f"/api/v1/budgets/reservations/{reservation.json()['id']}/settle", json={'actual_amount': '46', 'reason': 'Owner verified test charge'}, headers=headers | {'Idempotency-Key': str(uuid4())})
            assert settled.status_code == 200 and Decimal(settled.json()['actual_amount']) == Decimal('46')
            summary = client.get('/api/v1/budgets/current', headers=headers).json()
            assert summary['hard_stop'] is True and Decimal(summary['committed_amount']) == Decimal('46')
            body['task_id'] = str(uuid4())
            assert client.post('/api/v1/budgets/reservations', json=body, headers=headers | {'Idempotency-Key': str(uuid4())}).status_code == 409
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.postgres
def test_concurrent_budget_request_reuses_one_reservation_and_audit(monkeypatch):
    url = os.getenv('POSTGRES_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Isolated PostgreSQL required')
    engine = create_engine(url)
    monkeypatch.setattr(service, 'MONTHLY_ACCOUNT_NAME', f'idempotency-test-{uuid4()}')
    def database():
        with Session(engine, autoflush=False, expire_on_commit=False) as session:
            yield session
    app.dependency_overrides[get_db] = database
    token = str(uuid4())
    body = {'task_id': str(uuid4()), 'reserved_amount': '1', 'currency': 'USD', 'expires_at': (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}
    try:
        def reserve(_):
            with TestClient(app) as client:
                response = client.post('/api/v1/budgets/reservations', json=body, headers={'Authorization': 'Bearer test-owner-key', 'Idempotency-Key': token})
                assert response.status_code == 201, response.text
                return response.json()['id']
        with ThreadPoolExecutor(max_workers=4) as executor:
            ids = list(executor.map(reserve, range(4)))
        assert len(set(ids)) == 1
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(BudgetReservation).where(BudgetReservation.idempotency_key == token)) == 1
            from uuid import UUID
            assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == UUID(ids[0]), AuditEvent.action == 'budget_reservation.created')) == 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
