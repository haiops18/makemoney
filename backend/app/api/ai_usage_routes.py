"""Read-only AI usage and cost visibility; reconciliation stays in the finance API.

Token-derived cost is an estimate pending Owner reconciliation. Only a settled or
released reservation records a confirmed amount. Holds are amounts still reserved.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
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


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal('0.000001')))


@router.get('', response_model=UsageSummary)
def usage_summary(research_run_id: UUID | None = None, limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    statement = (select(AIInvocation, BudgetReservation, AIProvider, WorkflowTask)
                 .join(BudgetReservation, BudgetReservation.id == AIInvocation.reservation_id)
                 .join(AIProvider, AIProvider.id == AIInvocation.provider_id)
                 .join(TaskExecution, TaskExecution.id == AIInvocation.execution_id)
                 .join(WorkflowTask, WorkflowTask.id == TaskExecution.task_id)
                 .order_by(AIInvocation.created_at.desc(), AIInvocation.id))
    if research_run_id is not None:
        statement = statement.where(AIInvocation.research_run_id == research_run_id)
    rows = db.execute(statement.limit(10000)).all()
    zero = Decimal('0')
    by_status = {status: 0 for status in STATUSES}
    totals = {'estimated': zero, 'calculated': zero, 'confirmed': zero, 'held': zero, 'input': 0, 'output': 0, 'open': 0}
    groups: dict[str, dict[str, dict]] = {'role': {}, 'model': {}}
    items = []
    for invocation, reservation, provider, task in rows:
        closed = reservation.status in {'SETTLED', 'RELEASED'}
        confirmed = Decimal(reservation.actual_amount) if closed and reservation.actual_amount is not None else None
        held = zero if closed else Decimal(reservation.reserved_amount)
        calculated = Decimal(invocation.calculated_cost) if invocation.calculated_cost is not None else None
        # Any dispatch that reached a terminal state with an open hold needs the Owner.
        needs = not closed and invocation.status in {'SUCCEEDED', 'FAILED', 'USAGE_UNKNOWN'}
        by_status[invocation.status] = by_status.get(invocation.status, 0) + 1
        totals['estimated'] += Decimal(invocation.estimated_cost)
        totals['calculated'] += calculated or zero
        totals['confirmed'] += confirmed or zero
        totals['held'] += held
        totals['input'] += invocation.input_tokens or 0
        totals['output'] += invocation.output_tokens or 0
        totals['open'] += int(needs)
        for group, key in (('role', invocation.agent_role), ('model', f'{provider.kind}:{invocation.model_id}')):
            bucket = groups[group].setdefault(key, {'invocations': 0, 'input': 0, 'output': 0, 'calculated': zero, 'confirmed': zero})
            bucket['invocations'] += 1
            bucket['input'] += invocation.input_tokens or 0
            bucket['output'] += invocation.output_tokens or 0
            bucket['calculated'] += calculated or zero
            bucket['confirmed'] += confirmed or zero
        items.append(UsageItem(id=invocation.id, research_run_id=invocation.research_run_id, task_id=task.id, task_type=task.task_type,
                               agent_role=invocation.agent_role, provider_id=provider.id, provider_name=provider.name, provider_kind=provider.kind,
                               model_id=invocation.model_id, status=invocation.status, error_code=invocation.error_code,
                               input_tokens=invocation.input_tokens, output_tokens=invocation.output_tokens,
                               estimated_cost=_money(Decimal(invocation.estimated_cost)), calculated_cost=None if calculated is None else _money(calculated),
                               confirmed_cost=None if confirmed is None else _money(confirmed), reservation_id=reservation.id,
                               reservation_status=reservation.status, held_amount=_money(held), needs_reconciliation=needs,
                               created_at=invocation.created_at, completed_at=invocation.completed_at))

    def breakdown(group: str) -> list[Breakdown]:
        return [Breakdown(key=key, invocations=value['invocations'], input_tokens=value['input'], output_tokens=value['output'],
                          calculated_cost=_money(value['calculated']), confirmed_cost=_money(value['confirmed']))
                for key, value in sorted(groups[group].items())]

    return UsageSummary(invocations=len(rows), by_status=by_status, input_tokens=totals['input'], output_tokens=totals['output'],
                        estimated_cost=_money(totals['estimated']), calculated_cost=_money(totals['calculated']),
                        confirmed_cost=_money(totals['confirmed']), held_amount=_money(totals['held']), needs_reconciliation=totals['open'],
                        by_role=breakdown('role'), by_model=breakdown('model'), items=items[offset:offset + limit], total_items=len(items))
