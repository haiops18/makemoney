"""Opportunity ranking output (Step 7B discovery). Untrusted model output, validated by the server.

Every figure is an ESTIMATE with explicit assumptions; the server never treats it as fact.
Scores use the Opportunity Engine dimensions so an Owner-approved candidate can be
evaluated with the existing scoring rules.
"""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ai_brain.content_contract import _WEB_ADDRESS

SCORE_KEYS = ('market_demand', 'monetization_potential', 'automation_feasibility', 'experiment_cost', 'competitive_advantage', 'scalability', 'evidence_confidence')
BUSINESS_MODELS = ('AFFILIATE', 'CONTENT', 'SERVICE', 'DIGITAL_PRODUCT', 'ECOMMERCE', 'OTHER')
INTEGRATIONS = ('SEARCH', 'ACCESSTRADE', 'FACEBOOK_PAGE')
MAX_CANDIDATES = 8
MAX_VND = 10_000_000_000


class Scores(BaseModel):
    model_config = ConfigDict(extra='forbid')
    market_demand: int = Field(ge=0, le=100)
    monetization_potential: int = Field(ge=0, le=100)
    automation_feasibility: int = Field(ge=0, le=100)
    experiment_cost: int = Field(ge=0, le=100)
    competitive_advantage: int = Field(ge=0, le=100)
    scalability: int = Field(ge=0, le=100)
    evidence_confidence: int = Field(ge=0, le=100)


class Candidate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    business_model: Literal['AFFILIATE', 'CONTENT', 'SERVICE', 'DIGITAL_PRODUCT', 'ECOMMERCE', 'OTHER']
    summary: str = Field(min_length=1, max_length=2000)
    how_it_works: list[str] = Field(min_length=1, max_length=8)
    income_low_vnd: int = Field(ge=0, le=MAX_VND)
    income_base_vnd: int = Field(ge=0, le=MAX_VND)
    income_high_vnd: int = Field(ge=0, le=MAX_VND)
    startup_cost_vnd: int = Field(ge=0, le=MAX_VND)
    monthly_cost_vnd: int = Field(ge=0, le=MAX_VND)
    weeks_to_first_income: int = Field(ge=1, le=104)
    hours_per_week: int = Field(ge=0, le=80)
    success_likelihood: int = Field(ge=0, le=100)
    risk_level: Literal['LOW', 'MEDIUM', 'HIGH', 'SEVERE']
    risks: list[str] = Field(min_length=1, max_length=8)
    required_integrations: list[Literal['SEARCH', 'ACCESSTRADE', 'FACEBOOK_PAGE']] = Field(max_length=3)
    scores: Scores
    assumptions: list[str] = Field(min_length=1, max_length=10)
    source_ids: list[UUID] = Field(max_length=20)

    @model_validator(mode='after')
    def consistent(self):
        if not self.income_low_vnd <= self.income_base_vnd <= self.income_high_vnd:
            raise ValueError('Income range must be ordered low <= base <= high')
        texts = [self.title, self.summary, *self.how_it_works, *self.risks, *self.assumptions]
        if any(len(text) > 1000 for text in [*self.how_it_works, *self.risks, *self.assumptions]):
            raise ValueError('List items must be at most 1000 characters')
        if any(_WEB_ADDRESS.search(text) for text in texts):
            raise ValueError('Candidates must not contain web addresses')
        return self


class RankingOutput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    summary: str = Field(min_length=1, max_length=4000)
    candidates: list[Candidate] = Field(min_length=1, max_length=MAX_CANDIDATES)


def validate_ranking(raw: object, known_sources: set[UUID], _verified: set[UUID], _context: dict | None) -> RankingOutput:
    result = RankingOutput.model_validate(raw)
    for candidate in result.candidates:
        if not set(candidate.source_ids) <= known_sources:
            raise ValueError('Output contains unknown source references')
    if len({candidate.title.casefold() for candidate in result.candidates}) != len(result.candidates):
        raise ValueError('Candidates must have distinct titles')
    return result


def ranking_output_schema() -> dict:
    """Strict JSON schema (every property required, no extra properties)."""
    def strings(_max_items):
        return {'type': 'array', 'items': {'type': 'string'}}  # limits are enforced by the server
    integer = {'type': 'integer'}
    scores = {'type': 'object', 'additionalProperties': False, 'properties': {key: integer for key in SCORE_KEYS}, 'required': list(SCORE_KEYS)}
    properties = {
        'title': {'type': 'string'}, 'business_model': {'type': 'string', 'enum': list(BUSINESS_MODELS)}, 'summary': {'type': 'string'},
        'how_it_works': strings(8), 'income_low_vnd': integer, 'income_base_vnd': integer, 'income_high_vnd': integer, 'startup_cost_vnd': integer,
        'monthly_cost_vnd': integer, 'weeks_to_first_income': integer, 'hours_per_week': integer, 'success_likelihood': integer,
        'risk_level': {'type': 'string', 'enum': ['LOW', 'MEDIUM', 'HIGH', 'SEVERE']}, 'risks': strings(8),
        'required_integrations': {'type': 'array', 'items': {'type': 'string', 'enum': list(INTEGRATIONS)}},
        'scores': scores, 'assumptions': strings(10), 'source_ids': strings(20),
    }
    candidate = {'type': 'object', 'additionalProperties': False, 'properties': properties, 'required': list(properties)}
    return {'type': 'object', 'additionalProperties': False, 'required': ['summary', 'candidates'],
            'properties': {'summary': {'type': 'string'}, 'candidates': {'type': 'array', 'items': candidate}}}


def rank_value(candidate: dict) -> int:
    """Expected monthly income: base estimate weighted by the estimated likelihood."""
    return int(candidate['income_base_vnd']) * int(candidate['success_likelihood']) // 100
