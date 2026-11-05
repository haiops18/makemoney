from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Money = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6)]


class BudgetAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    currency: str
    period_start: datetime
    period_end: datetime
    limit_amount: Decimal
    reserve_amount: Decimal
    status: str


class BudgetSummaryResponse(BaseModel):
    account: BudgetAccountResponse
    committed_amount: Decimal
    available_amount: Decimal
    usage_percent: Decimal
    warning_thresholds_reached: list[int]
    hard_stop: bool


class BudgetReservationCreate(BaseModel):
    task_id: UUID
    reserved_amount: Money
    currency: Literal["USD"] = "USD"
    expires_at: datetime

    @field_validator('reserved_amount', mode='before')
    @classmethod
    def no_float_money(cls, value):
        if isinstance(value, float):
            raise ValueError('Use a decimal string for money')
        return value

    @field_validator("expires_at")
    @classmethod
    def future_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        if value <= datetime.now(value.tzinfo):
            raise ValueError("expires_at must be in the future")
        return value


class BudgetSettlement(BaseModel):
    actual_amount: Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6)]
    reason: str = Field(min_length=1, max_length=500)

    @field_validator('actual_amount', mode='before')
    @classmethod
    def no_float_money(cls, value):
        if isinstance(value, float):
            raise ValueError('Use a decimal string for money')
        return value


class BudgetReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    budget_account_id: UUID
    task_id: UUID
    reserved_amount: Decimal
    actual_amount: Decimal | None
    status: str
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class UsageRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    agent_run_id: UUID | None
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal
    actual_cost: Decimal | None
    currency: str
    recorded_at: datetime


class CostRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID | None
    task_id: UUID | None
    category: str
    provider: str
    amount: Decimal
    currency: str
    source: str
    status: str
    created_at: datetime
