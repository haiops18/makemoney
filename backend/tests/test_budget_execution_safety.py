from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import AuditEvent, BudgetAccount
from app.finance.service import MONTHLY_ACCOUNT_NAME, create_reservation, current_account, current_period


def test_monthly_account_conflict_does_not_rollback_outer_transaction(monkeypatch):
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(engine)
    start, end = current_period()
    with Session(engine, autoflush=False) as db:
        db.add(BudgetAccount(name=MONTHLY_ACCOUNT_NAME, period_start=start, period_end=end,
                             limit_amount=Decimal('50'), reserve_amount=Decimal('5')))
        db.commit()
        prior_id = uuid4()
        db.add(AuditEvent(id=prior_id, actor='owner', action='test.prior', entity_type='test', entity_id=uuid4(), detail={}))
        original = db.scalar
        calls = 0
        def missed_first_read(*args, **kwargs):
            nonlocal calls
            calls += 1
            return None if calls == 1 else original(*args, **kwargs)
        monkeypatch.setattr(db, 'scalar', missed_first_read)
        assert current_account(db, lock=True).name == MONTHLY_ACCOUNT_NAME
        assert db.get(AuditEvent, prior_id) is not None
        db.rollback()
        assert db.get(AuditEvent, prior_id) is None
    engine.dispose()


@pytest.mark.parametrize('amount', [0.1, Decimal('0'), Decimal('-1'), Decimal('NaN'), Decimal('0.0000001')])
def test_service_rejects_invalid_money_before_reserving(amount):
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        with pytest.raises(ValueError):
            create_reservation(db, uuid4(), 'test-key', amount, datetime.now(UTC) + timedelta(minutes=5), 'owner')
        assert db.scalar(select(BudgetAccount)) is None
    engine.dispose()


def test_service_rejects_expired_or_closed_budget():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        with pytest.raises(ValueError):
            create_reservation(db, uuid4(), 'bad-expiry', Decimal('1'), datetime.now(UTC) - timedelta(seconds=1), 'owner')
        account = current_account(db, lock=True)
        account.status = 'CLOSED'
        db.flush()
        with pytest.raises(ValueError, match='not active'):
            create_reservation(db, uuid4(), 'closed', Decimal('1'), datetime.now(UTC) + timedelta(minutes=5), 'owner')
    engine.dispose()
