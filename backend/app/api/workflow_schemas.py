from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkflowCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    opportunity_id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class WorkflowUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    opportunity_id: UUID | None
    research_run_id: UUID | None = None
    name: str
    description: str | None
    status: str
    created_by: str
    version: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    task_count: int = 0
    succeeded_tasks: int = 0
    last_execution: datetime | None = None


class WorkflowList(BaseModel):
    items: list[WorkflowResponse]
    total: int
    limit: int
    offset: int


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    task_type: Literal['VALIDATE_OPPORTUNITY', 'VALIDATE_EVIDENCE', 'VALIDATE_RESEARCH_DRAFT']
    assigned_role: str = Field(min_length=1, max_length=100)
    priority: int = Field(default=0, ge=-100, le=100)
    max_retries: int = Field(default=0, ge=0, le=10)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    depends_on: list[UUID] = Field(default_factory=list, max_length=100)


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    workflow_id: UUID
    name: str
    description: str | None
    task_type: str
    assigned_role: str
    status: str
    priority: int
    max_retries: int
    retry_count: int
    timeout_seconds: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    next_retry_at: datetime | None
    depends_on: list[UUID] = Field(default_factory=list)


class WorkflowSubmit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    policy_id: UUID
    expires_at: datetime

    @field_validator('expires_at')
    @classmethod
    def future_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value <= datetime.now(UTC):
            raise ValueError('expires_at must be a future timezone-aware timestamp')
        return value


class WorkflowSubmission(BaseModel):
    workflow: WorkflowResponse
    approval_id: UUID
    action_hash: str


class WorkflowEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    workflow_id: UUID
    task_id: UUID | None
    event_type: str
    previous_status: str | None
    new_status: str | None
    actor: str
    created_at: datetime
    metadata_json: dict


class TaskExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    workflow_id: UUID | None = None
    task_id: UUID
    attempt_number: int
    status: str
    started_at: datetime
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None
    output_reference: str | None
    output_json: dict | None
    input_fields: list[str] = Field(default_factory=list)


class TaskQueueRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    policy_id: UUID
    approval_id: UUID
