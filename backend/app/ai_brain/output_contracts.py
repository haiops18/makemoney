"""Output contracts by prompt family. Each has a strict JSON schema and a server validator.

The research contract is unchanged from v29: research requests and action payloads stay
byte-identical, so existing approvals and auto-run plan hashes remain valid.
"""
from dataclasses import dataclass
from typing import Callable
from uuid import UUID

from pydantic import BaseModel

from app.ai_brain.content_contract import content_output_schema, validate_content
from app.ai_brain.contracts import research_output_schema, validate_output


@dataclass(frozen=True)
class OutputContract:
    name: str
    schema: Callable[[], dict]
    validate: Callable[[object, set[UUID], set[UUID], dict], BaseModel]


RESEARCH = OutputContract('research_output', research_output_schema, lambda raw, known, verified, _context: validate_output(raw, known, verified))
CONTENT_DRAFT = OutputContract('content_draft', content_output_schema, validate_content)
CONTRACTS = {RESEARCH.name: RESEARCH, CONTENT_DRAFT.name: CONTENT_DRAFT}
# Prompt families whose output is not a research result. Every other family is research.
PROMPT_CONTRACTS = {'content_draft': CONTENT_DRAFT}


def contract_for_prompt(prompt_name: str) -> OutputContract:
    return PROMPT_CONTRACTS.get(prompt_name, RESEARCH)


def contract_named(name: str | None) -> OutputContract:
    """Payloads without an explicit contract are research payloads (v29 format)."""
    if name is None:
        return RESEARCH
    if name not in CONTRACTS:
        raise ValueError('Unknown output contract')
    return CONTRACTS[name]
