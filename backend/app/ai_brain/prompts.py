"""Versioned prompt envelope; evidence remains untrusted input, never instructions."""
from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvidenceInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    source_id: UUID
    text: str = Field(min_length=1, max_length=12000)


class PriorFinding(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    classification: str = Field(min_length=1, max_length=20)
    statement: str = Field(min_length=1, max_length=4000)
    source_ids: list[UUID] = Field(default_factory=list, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=20)


class PriorStageOutput(BaseModel):
    """Validated output of an earlier AI stage. It is model-generated and untrusted."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    stage: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=8000)
    findings: list[PriorFinding] = Field(default_factory=list, max_length=100)


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    objective: str = Field(min_length=1, max_length=4000)
    target_market: str | None = Field(default=None, max_length=200)
    target_customers: str | None = Field(default=None, max_length=500)
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=20)
    prior_outputs: list[PriorStageOutput] = Field(default_factory=list, max_length=10)


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    system: str
    developer: str

    def messages(self, request: ResearchRequest) -> list[dict[str, str]]:
        if not all((self.name.strip(), self.version.strip(), self.system.strip(), self.developer.strip())):
            raise ValueError('Versioned prompt instructions are required')
        # Untrusted evidence and the Owner request are serialized as one user
        # message; their content never becomes a system or developer instruction.
        return [
            {'role': 'system', 'content': self.system},
            {'role': 'developer', 'content': self.developer},
            {'role': 'user', 'content': request.model_dump_json()},
        ]
