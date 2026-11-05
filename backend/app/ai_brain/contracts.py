"""Untrusted model output contracts; verification is performed by the server."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Finding(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    classification: Literal['FACT', 'ESTIMATE', 'HYPOTHESIS', 'UNKNOWN']
    statement: str = Field(min_length=1, max_length=4000)
    source_ids: list[UUID] = Field(default_factory=list, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def require_support(self):
        if self.classification == 'FACT' and not self.source_ids:
            raise ValueError('A fact requires at least one source reference')
        if self.classification == 'ESTIMATE' and not self.assumptions:
            raise ValueError('An estimate requires explicit assumptions')
        return self


class ResearchOutput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    summary: str = Field(min_length=1, max_length=8000)
    findings: list[Finding] = Field(max_length=100)


def validate_output(raw: object, known_sources: set[UUID], verified_sources: set[UUID]) -> ResearchOutput:
    """Reject invented citations and unsupported facts, including extra fields."""
    result = ResearchOutput.model_validate(raw)
    for finding in result.findings:
        references = set(finding.source_ids)
        if not references <= known_sources:
            raise ValueError('Output contains unknown source references')
        if finding.classification == 'FACT' and not references <= verified_sources:
            raise ValueError('A fact requires verified sources')
    return result
