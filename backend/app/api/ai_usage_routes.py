"""Read-only AI usage and cost visibility; reconciliation stays in the finance API.

Token-derived cost is an estimate pending Owner reconciliation. Only a settled or
released reservation records a confirmed amount. Holds are amounts still reserved.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Numeric, and_, case, cast, func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_owner
from app.db.models import AIInvocation, AIProvider, BudgetReservation, TaskExecution, WorkflowTask
from app.db.session import get_db

router = APIRouter(prefix='/api/v1/ai/usage', dependencies=[Depends(require_owner)], tags=['ai-usage'])

STATUSES = ('PREPARED', 'DISPATCHED', 'SUCCEEDED', 'FAILED', 'USAGE_UNKNOWN')


class UsageItem(BaseModel):
    id: UUID
    research_run_id: UUID
    task_id: UUID
    task_type: str
    agent_role: str
    provider_id: UUID
    provider_name: str
    provider_kind: str
    model_id: str
    status: str
    error_code: str | None
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost: str
    calculated_cost: str | None
    confirmed_cost: str | None
    reservation_id: UUID
    reservation_status: str
    held_amount: str
    needs_reconciliation: bool
    created_at: datetime
    completed_at: datetime | None


class Breakdown(BaseModel):
    key: str
    invocations: int
    input_tokens: int
    output_tokens: int
    calculated_cost: str
    confirmed_cost: str


class UsageSummary(BaseModel):
    currency: str = 'USD'
    invocations: int
    by_status: dict[str, int]
    input_tokens: int
    output_tokens: int
    estimated_cost: str
    calculated_cost: str
    confirmed_cost: str
    held_amount: str
    needs_reconciliation: int
    by_role: list[Breakdown]
    by_model: list[Breakdown]
    items: list[UsageItem]
    total_items: int


def _money(value) -> str:
    return str(Decimal(value or 0).quantize(Decimal('0.000001')))


MONEY = Numeric(18, 6)
CLOSED = BudgetReservation.status.in_(['SETTLED', 'RELEASED'])
CONFIRMED = case((CLOSED, func.coalesce(BudgetReservation.actual_amount, 0)), else_=0)
HELD = case((CLOSED, 0), else_=BudgetReservation.reserved_amount)
# Any dispatch that reached a terminal state with an open hold needs the Owner.
NEEDS = case((and_(~CLOSED, AIInvocation.status.in_(['SUCCEEDED', 'FAILED', 'USAGE_UNKNOWN'])), 1), else_=0)


def _scoped(statement, research_run_id: UUID | None):
    statement = statement.select_from(AIInvocation).join(BudgetReservation, BudgetReservation.id == AIInvocation.reservation_id)
    return statement.where(AIInvocation.research_run_id == research_run_id) if research_run_id is not None else statement


def _totals():
    return (func.count(AIInvocation.id), func.coalesce(func.sum(func.coalesce(AIInvocation.input_tokens, 0)), 0),
            func.coalesce(func.sum(func.coalesce(AIInvocation.output_tokens, 0)), 0),
            cast(func.coalesce(func.sum(func.coalesce(AIInvocation.calculated_cost, 0)), 0), MONEY), cast(func.coalesce(func.sum(CONFIRMED), 0), MONEY))


@router.get('', response_model=UsageSummary)
def usage_summary(research_run_id: UUID | None = None, limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    """All totals are computed in SQL over every matching invocation; only items are paginated."""
    count, input_tokens, output_tokens, calculated, confirmed = db.execute(_scoped(select(*_totals()), research_run_id)).one()
    estimated, held, needs = db.execute(_scoped(select(cast(func.coalesce(func.sum(AIInvocation.estimated_cost), 0), MONEY),
                                                       cast(func.coalesce(func.sum(HELD), 0), MONEY), func.coalesce(func.sum(NEEDS), 0)), research_run_id)).one()
    by_status = {status: 0 for status in STATUSES}
    for status, total in db.execute(_scoped(select(AIInvocation.status, func.count(AIInvocation.id)), research_run_id).group_by(AIInvocation.status)):
        by_status[status] = total

    def breakdown(*columns) -> list[Breakdown]:
        rows = db.execute(_scoped(select(*columns, *_totals()), research_run_id).join(AIProvider, AIProvider.id == AIInvocation.provider_id)
                          .group_by(*columns).order_by(*columns))
        return [Breakdown(key=':'.join(str(part) for part in row[:len(columns)]), invocations=row[-5], input_tokens=row[-4], output_tokens=row[-3],
                          calculated_cost=_money(row[-2]), confirmed_cost=_money(row[-1])) for row in rows]

    page = db.execute(_scoped(select(AIInvocation, BudgetReservation, AIProvider, WorkflowTask), research_run_id)
                      .join(AIProvider, AIProvider.id == AIInvocation.provider_id)
                      .join(TaskExecution, TaskExecution.id == AIInvocation.execution_id)
                      .join(WorkflowTask, WorkflowTask.id == TaskExecution.task_id)
                      .order_by(AIInvocation.created_at.desc(), AIInvocation.id).offset(offset).limit(limit)).all()
    items = []
    for invocation, reservation, provider, task in page:
        closed = reservation.status in {'SETTLED', 'RELEASED'}
        actual = reservation.actual_amount if closed and reservation.actual_amount is not None else None
        items.append(UsageItem(id=invocation.id, research_run_id=invocation.research_run_id, task_id=task.id, task_type=task.task_type,
                               agent_role=invocation.agent_role, provider_id=provider.id, provider_name=provider.name, provider_kind=provider.kind,
                               model_id=invocation.model_id, status=invocation.status, error_code=invocation.error_code,
                               input_tokens=invocation.input_tokens, output_tokens=invocation.output_tokens,
                               estimated_cost=_money(invocation.estimated_cost), calculated_cost=None if invocation.calculated_cost is None else _money(invocation.calculated_cost),
                               confirmed_cost=None if actual is None else _money(actual), reservation_id=reservation.id,
                               reservation_status=reservation.status, held_amount=_money(0 if closed else reservation.reserved_amount),
                               needs_reconciliation=not closed and invocation.status in {'SUCCEEDED', 'FAILED', 'USAGE_UNKNOWN'},
                               created_at=invocation.created_at, completed_at=invocation.completed_at))
    return UsageSummary(invocations=count, by_status=by_status, input_tokens=input_tokens, output_tokens=output_tokens,
                        estimated_cost=_money(estimated), calculated_cost=_money(calculated), confirmed_cost=_money(confirmed),
                        held_amount=_money(held), needs_reconciliation=needs, by_role=breakdown(AIInvocation.agent_role),
                        by_model=breakdown(AIProvider.kind, AIInvocation.model_id), items=items, total_items=count)
