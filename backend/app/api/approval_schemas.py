from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    version: str
    description: str
    rules_json: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class PolicyEvaluationRequest(BaseModel):
    policy_id: UUID
    action_type: str = Field(min_length=1, max_length=100)
    action_payload: dict[str, Any]
    resource_type: str = Field(min_length=1, max_length=100)
    resource_id: UUID
    scope: Literal["ONCE"] = "ONCE"


class PolicyEvaluationResponse(BaseModel):
    allowed: bool
    reason: str
    action_hash: str
    policy_id: UUID
    policy_version: str | None
    requires_approval: bool = True


class ApprovalCreate(PolicyEvaluationRequest):
    reason: str | None = Field(default=None, max_length=500)
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def expiry_must_be_future(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value <= datetime.now(UTC):
            raise ValueError("expires_at must be a future timezone-aware timestamp")
        return value


class ApprovalDecisionInput(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_id: UUID
    policy_version: str
    action_type: str
    action_hash: str
    action_payload_json: dict[str, Any]
    resource_type: str
    resource_id: UUID
    requested_by: str
    status: str
    reason: str | None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class ApprovalListResponse(BaseModel):
    items: list[ApprovalResponse]
