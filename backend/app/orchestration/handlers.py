"""Pure internal handlers. These perform no network, shell, AI or database writes.

Calling a handler does not authorize a task execution; a future execution boundary
must enforce owner, policy, approval, budget, dependencies and lease ownership.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OpportunityInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    title: str = Field(min_length=1, max_length=200)
    business_model: str = Field(min_length=1, max_length=100)
    target_market: str | None = Field(default=None, max_length=200)


class EvidenceInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    evidence_count: int = Field(ge=0, le=1000000)
    verified_count: int = Field(ge=0, le=1000000)


class ValidationResult(BaseModel):
    status: Literal['COMPLETE', 'INCOMPLETE']
    missing: list[str]


def dispatch(task_type: str, payload: dict) -> ValidationResult:
    if task_type == 'VALIDATE_OPPORTUNITY':
        item = OpportunityInput.model_validate(payload)
        missing = [] if item.target_market and item.target_market.strip() else ['target_market']
    elif task_type == 'VALIDATE_EVIDENCE':
        item = EvidenceInput.model_validate(payload)
        if item.verified_count > item.evidence_count:
            raise ValueError('verified_count cannot exceed evidence_count')
        missing = [] if item.verified_count else ['verified_evidence']
    else:
        raise ValueError('Task type is not an allowed internal handler')
    return ValidationResult(status='INCOMPLETE' if missing else 'COMPLETE', missing=missing)
