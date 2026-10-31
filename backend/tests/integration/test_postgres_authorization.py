import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.approvals.service import consume_action_authorization
from app.db.models import ActionAuthorization, ApprovalRequest, AuditEvent, BudgetReservation, Policy
from app.finance.service import create_reservation, current_account


@pytest.mark.postgres
def test_one_time_authorization_is_atomic_on_postgresql():
    database_url = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not configured")

    engine = create_engine(database_url, pool_pre_ping=True)
    approval_id = uuid4()
    authorization_id = uuid4()
    with Session(engine) as session:
        policy = session.scalar(select(Policy).where(Policy.name == "owner-controlled-internal"))
        assert policy is not None
        approval = ApprovalRequest(
            id=approval_id,
            policy_id=policy.id,
            policy_version=policy.version,
            action_type="INTERNAL_WORKFLOW",
            action_hash="a" * 64,
            action_payload_json={"test": "postgres-concurrency"},
            resource_type="workflow",
            resource_id=uuid4(),
            requested_by="postgres-test",
            status="APPROVED",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        session.add(approval)
        session.flush()
        session.add(ActionAuthorization(id=authorization_id, approval_id=approval.id, action_hash=approval.action_hash, scope="ONCE", expires_at=approval.expires_at))
        session.commit()

    def consume_once() -> bool:
        with Session(engine) as session:
            consumed = consume_action_authorization(session, authorization_id, "a" * 64, "postgres-test")
            session.commit()
            return consumed

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: consume_once(), range(2)))
        assert sorted(results) == [False, True]
    finally:
        with Session(engine) as session:
            session.execute(delete(AuditEvent).where(AuditEvent.entity_id == authorization_id))
            session.execute(delete(ActionAuthorization).where(ActionAuthorization.id == authorization_id))
            session.execute(delete(ApprovalRequest).where(ApprovalRequest.id == approval_id))
            session.commit()


@pytest.mark.postgres
def test_budget_reservation_is_atomic_on_postgresql():
    database_url = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not configured")

    engine = create_engine(database_url, pool_pre_ping=True)
    with Session(engine) as session:
        current_account(session)
        session.commit()

    task_ids = [uuid4(), uuid4()]
    reservation_ids = []

    def reserve_once(task_id) -> bool:
        with Session(engine) as session:
            try:
                reservation = create_reservation(session, task_id, f"postgres-budget-{task_id}", Decimal("30"), datetime.now(UTC) + timedelta(minutes=5), "postgres-test")
                reservation_ids.append(reservation.id)
                session.commit()
                return True
            except ValueError:
                session.rollback()
                return False

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(reserve_once, task_ids))
        assert sorted(results) == [False, True]
    finally:
        with Session(engine) as session:
            session.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(reservation_ids)))
            session.execute(delete(BudgetReservation).where(BudgetReservation.id.in_(reservation_ids)))
            session.commit()
