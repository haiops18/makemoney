from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AuditEvent, BudgetAccount, BudgetReservation

MONTHLY_ACCOUNT_NAME = "monthly-controlled-autonomy"
HCM = ZoneInfo("Asia/Ho_Chi_Minh")


def now_utc() -> datetime:
    return datetime.now(UTC)


def current_period(now: datetime | None = None) -> tuple[datetime, datetime]:
    local = (now or now_utc()).astimezone(HCM)
    start_local = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start_local.month == 12:
        end_local = start_local.replace(year=start_local.year + 1, month=1)
    else:
        end_local = start_local.replace(month=start_local.month + 1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def current_account(db: Session, *, lock: bool = False) -> BudgetAccount:
    start, end = current_period()
    statement = select(BudgetAccount).where(BudgetAccount.name == MONTHLY_ACCOUNT_NAME, BudgetAccount.period_start == start)
    if lock:
        statement = statement.with_for_update()
    account = db.scalar(statement)
    if account:
        return account
    settings = get_settings()
    account = BudgetAccount(name=MONTHLY_ACCOUNT_NAME, period_start=start, period_end=end, limit_amount=Decimal(str(settings.monthly_budget_usd)), reserve_amount=Decimal(str(settings.budget_reserve_usd)))
    try:
        # A concurrent request can create the same month. Roll back only the
        # insert savepoint, not the outer transaction containing other controls.
        with db.begin_nested():
            db.add(account)
            db.flush()
        return account
    except IntegrityError:
        account = db.scalar(statement)
        if account is None:
            raise
        return account


def expire_reservations(db: Session, account_id, actor: str) -> None:
    expired = list(db.scalars(select(BudgetReservation).where(BudgetReservation.budget_account_id == account_id, BudgetReservation.status == "ACTIVE", BudgetReservation.expires_at <= now_utc()).with_for_update()))
    for reservation in expired:
        reservation.status = "EXPIRED"
        db.add(AuditEvent(actor=actor, action="budget_reservation.expired", entity_type="budget_reservation", entity_id=reservation.id, detail={"reserved_amount": str(reservation.reserved_amount)}))
    if expired:
        db.flush()


def committed_amount(db: Session, account_id) -> Decimal:
    reservations = db.scalars(select(BudgetReservation).where(BudgetReservation.budget_account_id == account_id)).all()
    total = Decimal("0")
    for reservation in reservations:
        if reservation.status in {"ACTIVE", "EXPIRED"}:
            total += Decimal(reservation.reserved_amount)
        else:
            total += Decimal(reservation.actual_amount or 0)
    return total


def budget_summary(db: Session, account: BudgetAccount) -> dict:
    committed = committed_amount(db, account.id)
    limit = Decimal(account.limit_amount)
    reserve = Decimal(account.reserve_amount)
    available = max(Decimal("0"), limit - reserve - committed)
    percent = (committed / limit * 100) if limit else Decimal("100")
    warnings = [threshold for threshold in (50, 75, 90) if percent >= threshold]
    return {
        "account": account,
        "committed_amount": committed,
        "available_amount": available,
        "usage_percent": percent,
        "warning_thresholds_reached": warnings,
        "hard_stop": committed + reserve >= limit,
    }


def create_reservation(db: Session, task_id: UUID, idempotency_key: str, amount: Decimal, expires_at: datetime, actor: str) -> BudgetReservation:
    if (not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0
        or amount.as_tuple().exponent < -6 or amount >= Decimal('1000000000000')):
        raise ValueError('Reservation amount must be a positive USD Decimal with at most six decimal places')
    if expires_at.tzinfo is None or expires_at.utcoffset() is None or expires_at <= now_utc():
        raise ValueError('Reservation expiry must be a future timezone-aware timestamp')
    account = current_account(db, lock=True)
    if account.status != 'ACTIVE':
        raise ValueError('Budget account is not active')
    expire_reservations(db, account.id, actor)
    if amount > budget_summary(db, account)["available_amount"]:
        raise ValueError("Insufficient available budget")
    duplicate = db.scalar(select(BudgetReservation).where(BudgetReservation.budget_account_id == account.id, BudgetReservation.task_id == task_id))
    if duplicate:
        raise ValueError("A reservation already exists for this task")
    reservation = BudgetReservation(budget_account_id=account.id, task_id=task_id, idempotency_key=idempotency_key, reserved_amount=amount, expires_at=expires_at)
    db.add(reservation)
    db.flush()
    db.add(AuditEvent(actor=actor, action="budget_reservation.created", entity_type="budget_reservation", entity_id=reservation.id, detail={"task_id": str(reservation.task_id), "reserved_amount": str(reservation.reserved_amount)}))
    return reservation
