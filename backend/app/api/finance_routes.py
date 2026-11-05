import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.finance_schemas import BudgetAccountResponse, BudgetReservationCreate, BudgetReservationResponse, BudgetSettlement, BudgetSummaryResponse, CostRecordResponse, UsageRecordResponse
from app.auth.dependencies import require_owner
from app.db.models import AuditEvent, BudgetAccount, BudgetReservation, CostRecord, IdempotencyRecord, UsageRecord
from app.db.session import get_db
from app.finance.service import budget_summary, create_reservation, current_account, expire_reservations

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_owner)])


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _idempotent(db: Session, actor: str, key: str, path: str, payload: dict) -> BudgetReservationResponse | None:
    if db.bind is not None and db.bind.dialect.name == 'postgresql':
        lock_id = int.from_bytes(hashlib.sha256(f'{actor}:{key}'.encode()).digest()[:8], 'big', signed=True)
        db.execute(text('SELECT pg_advisory_xact_lock(:lock_id)'), {'lock_id': lock_id})
    request_hash = _hash(payload)
    record = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.actor == actor, IdempotencyRecord.key == key))
    if record is None:
        return None
    if (record.method, record.path, record.request_hash) != ("POST", path, request_hash):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key was used for another request")
    return BudgetReservationResponse.model_validate(record.response_body)


def _store_response(db: Session, actor: str, key: str, path: str, payload: dict, reservation: BudgetReservation, code: int) -> BudgetReservationResponse:
    response = BudgetReservationResponse.model_validate(reservation)
    db.add(IdempotencyRecord(actor=actor, key=key, method="POST", path=path, request_hash=_hash(payload), status_code=code, response_body=response.model_dump(mode="json")))
    return response


@router.get("/budgets", response_model=list[BudgetAccountResponse])
def list_budgets(db: Session = Depends(get_db)) -> list[BudgetAccount]:
    return list(db.scalars(select(BudgetAccount).order_by(BudgetAccount.period_start.desc())))


@router.get("/budgets/current", response_model=BudgetSummaryResponse)
def get_current_budget(db: Session = Depends(get_db)) -> BudgetSummaryResponse:
    account = current_account(db)
    db.commit()
    return BudgetSummaryResponse(**budget_summary(db, account))


@router.post("/budgets/reservations", response_model=BudgetReservationResponse, status_code=status.HTTP_201_CREATED)
def reserve_budget(request: BudgetReservationCreate, response: Response, idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> BudgetReservationResponse:
    path = "/api/v1/budgets/reservations"
    payload = request.model_dump(mode="json")
    existing = _idempotent(db, actor, idempotency_key, path, payload)
    if existing:
        response.status_code = status.HTTP_201_CREATED
        return existing
    try:
        reservation = create_reservation(db, request.task_id, idempotency_key, request.reserved_amount, request.expires_at, actor)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    result = _store_response(db, actor, idempotency_key, path, payload, reservation, 201)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _idempotent(db, actor, idempotency_key, path, payload)
        if existing:
            response.status_code = status.HTTP_201_CREATED
            return existing
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unable to reserve budget")
    return result


def _close_reservation(reservation_id: UUID, outcome: str, body: BudgetSettlement, response: Response, idempotency_key: str, actor: str, db: Session) -> BudgetReservationResponse:
    path = f"/api/v1/budgets/reservations/{reservation_id}/{outcome.lower()}"
    payload = body.model_dump(mode="json")
    existing = _idempotent(db, actor, idempotency_key, path, payload)
    if existing:
        return existing
    initial = db.get(BudgetReservation, reservation_id)
    if initial is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget reservation not found")
    account = db.scalar(select(BudgetAccount).where(BudgetAccount.id == initial.budget_account_id).with_for_update())
    reservation = db.scalar(select(BudgetReservation).where(BudgetReservation.id == reservation_id).with_for_update())
    expire_reservations(db, account.id, actor)
    if reservation.status not in {"ACTIVE", "EXPIRED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Budget reservation is not open")
    if outcome == 'RELEASED' and body.actual_amount > reservation.reserved_amount:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Over-budget charges must be settled, not released")
    reservation.actual_amount = body.actual_amount
    reservation.status = outcome
    db.flush()
    result = _store_response(db, actor, idempotency_key, path, payload, reservation, 200)
    db.add(AuditEvent(actor=actor, action=f"budget_reservation.{outcome.lower()}", entity_type="budget_reservation", entity_id=reservation.id, detail={"actual_amount": str(body.actual_amount), "reason": body.reason, "over_reserved": body.actual_amount > reservation.reserved_amount}))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _idempotent(db, actor, idempotency_key, path, payload)
        if existing:
            return existing
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Budget reservation was changed concurrently")
    return result


@router.post("/budgets/reservations/{reservation_id}/settle", response_model=BudgetReservationResponse)
def settle_reservation(reservation_id: UUID, body: BudgetSettlement, response: Response, idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> BudgetReservationResponse:
    return _close_reservation(reservation_id, "SETTLED", body, response, idempotency_key, actor, db)


@router.post("/budgets/reservations/{reservation_id}/release", response_model=BudgetReservationResponse)
def release_reservation(reservation_id: UUID, body: BudgetSettlement, response: Response, idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> BudgetReservationResponse:
    return _close_reservation(reservation_id, "RELEASED", body, response, idempotency_key, actor, db)


@router.get("/finance/usage", response_model=list[UsageRecordResponse])
def list_usage(db: Session = Depends(get_db)) -> list[UsageRecord]:
    return list(db.scalars(select(UsageRecord).order_by(UsageRecord.recorded_at.desc()).limit(100)))


@router.get("/finance/costs", response_model=list[CostRecordResponse])
def list_costs(db: Session = Depends(get_db)) -> list[CostRecord]:
    return list(db.scalars(select(CostRecord).order_by(CostRecord.created_at.desc()).limit(100)))
