"""Step 7A content-draft input and output contracts. Model output is untrusted.

The model never sees an affiliate URL: it writes the placeholder below and the server
substitutes the Owner's stored link only when an approved item is exported. Any URL or
web address the model writes is rejected, so it cannot invent or alter a link.
"""
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

LINK_PLACEHOLDER = '{{AFFILIATE_LINK}}'
CONTENT_TYPES = ('REVIEW_ARTICLE', 'COMPARISON', 'VIDEO_SCRIPT', 'SHORT_CAPTION', 'SOCIAL_POST', 'CTA_LANDING')
ContentType = Literal['REVIEW_ARTICLE', 'COMPARISON', 'VIDEO_SCRIPT', 'SHORT_CAPTION', 'SOCIAL_POST', 'CTA_LANDING']
# App limits for a reviewable draft, not platform rules.
BODY_LIMITS = {'REVIEW_ARTICLE': 8000, 'COMPARISON': 8000, 'VIDEO_SCRIPT': 6000, 'SHORT_CAPTION': 600, 'SOCIAL_POST': 3000, 'CTA_LANDING': 3000}
MAX_ITEMS = 10
_WEB_ADDRESS = re.compile(r'(?i)\b(?:https?://|www\.)|\b[a-z0-9-]+\.(?:vn|com|net|org|ee|io|co|shop|link|me|ly)(?:/|\b)')


class TermInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    term: str = Field(min_length=1, max_length=40)
    value_text: str = Field(min_length=1, max_length=1000)
    value_numeric: str | None = Field(default=None, max_length=40)
    unit: str = Field(min_length=1, max_length=10)
    evidence_status: Literal['VERIFIED', 'UNVERIFIED', 'UNSOURCED']
    source_id: UUID | None = None


class ProductInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=300)
    merchant: str | None = Field(default=None, max_length=200)
    price_text: str | None = Field(default=None, max_length=100)
    price_evidence_status: Literal['VERIFIED', 'UNVERIFIED', 'UNSOURCED']
    price_source_id: UUID | None = None


class EvidenceInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    source_id: UUID
    verification_status: Literal['VERIFIED', 'UNVERIFIED']
    text: str = Field(min_length=1, max_length=12000)


class ContentRequest(BaseModel):
    """Everything the model may see. Campaign data is Owner-entered and untrusted as instructions."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    language: Literal['vi', 'en']
    campaign_name: str = Field(min_length=1, max_length=200)
    niche: str | None = Field(default=None, max_length=200)
    target_audience: str | None = Field(default=None, max_length=500)
    goal: str | None = Field(default=None, max_length=2000)
    network: str = Field(min_length=1, max_length=30)
    program_name: str = Field(min_length=1, max_length=200)
    product: ProductInput | None = None
    terms: list[TermInput] = Field(default_factory=list, max_length=20)
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=20)
    content_types: list[ContentType] = Field(min_length=1, max_length=len(CONTENT_TYPES))
    count_per_type: int = Field(ge=1, le=3)
    link_placeholder: Literal['{{AFFILIATE_LINK}}'] = LINK_PLACEHOLDER


class Claim(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    classification: Literal['FACT', 'ESTIMATE', 'HYPOTHESIS']
    statement: str = Field(min_length=1, max_length=1000)
    source_ids: list[UUID] = Field(default_factory=list, max_length=10)

    @model_validator(mode='after')
    def fact_needs_source(self):
        if self.classification == 'FACT' and not self.source_ids:
            raise ValueError('A factual claim requires a source reference')
        return self


class ContentItemOutput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    content_type: ContentType
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)
    hashtags: list[str] = Field(default_factory=list, max_length=15)
    cta: str = Field(min_length=1, max_length=300)
    claims: list[Claim] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def within_limits(self):
        if len(self.body) > BODY_LIMITS[self.content_type]:
            raise ValueError('Content body exceeds the limit for its type')
        if any(not tag or len(tag) > 50 or any(char.isspace() for char in tag) for tag in self.hashtags):
            raise ValueError('Hashtags must be single words of at most 50 characters')
        return self


class ContentDraftOutput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    summary: str = Field(min_length=1, max_length=2000)
    items: list[ContentItemOutput] = Field(min_length=1, max_length=MAX_ITEMS)


def content_output_schema() -> dict:
    claim = {'type': 'object', 'additionalProperties': False,
             'properties': {'classification': {'type': 'string', 'enum': ['FACT', 'ESTIMATE', 'HYPOTHESIS']}, 'statement': {'type': 'string'},
                            'source_ids': {'type': 'array', 'items': {'type': 'string'}}},
             'required': ['classification', 'statement', 'source_ids']}
    item = {'type': 'object', 'additionalProperties': False,
            'properties': {'content_type': {'type': 'string', 'enum': list(CONTENT_TYPES)}, 'title': {'type': 'string'}, 'body': {'type': 'string'},
                           'hashtags': {'type': 'array', 'items': {'type': 'string'}}, 'cta': {'type': 'string'}, 'claims': {'type': 'array', 'items': claim}},
            'required': ['content_type', 'title', 'body', 'hashtags', 'cta', 'claims']}
    return {'type': 'object', 'additionalProperties': False,
            'properties': {'summary': {'type': 'string'}, 'items': {'type': 'array', 'items': item}}, 'required': ['summary', 'items']}


def validate_content(raw: object, known_sources: set[UUID], verified_sources: set[UUID], context: dict) -> ContentDraftOutput:
    """Reject invented citations, unsupported facts, missing link placeholders and any web address."""
    result = ContentDraftOutput.model_validate(raw)
    allowed = set(context.get('content_types') or ())
    expected = context.get('expected_items')
    if not allowed or not isinstance(expected, int) or len(result.items) != expected:
        raise ValueError('Output does not contain the requested number of items')
    for item in result.items:
        if item.content_type not in allowed:
            raise ValueError('Output contains a content type that was not requested')
        if LINK_PLACEHOLDER not in item.body and LINK_PLACEHOLDER not in item.cta:
            raise ValueError('Every item needs the affiliate link placeholder')
        text = ' '.join([item.title, item.body.replace(LINK_PLACEHOLDER, ''), item.cta.replace(LINK_PLACEHOLDER, ''), *item.hashtags])
        if _WEB_ADDRESS.search(text):
            raise ValueError('Output must not contain web addresses')
        for claim in item.claims:
            references = set(claim.source_ids)
            if not references <= known_sources:
                raise ValueError('Output contains unknown source references')
            if claim.classification == 'FACT' and not references <= verified_sources:
                raise ValueError('A factual claim requires verified sources')
    return result
