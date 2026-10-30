from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    role: str
    model: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class AgentUpdate(BaseModel):
    enabled: bool


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor: str
    action: str
    entity_type: str
    entity_id: UUID
    detail: dict
    timestamp: datetime


class DashboardResponse(BaseModel):
    agents_total: int
    agents_enabled: int
    audit_events_last_24h: int
    monthly_budget_usd: int
    timezone: str
    external_execution_enabled: bool = False


class MessageResponse(BaseModel):
    message: str
