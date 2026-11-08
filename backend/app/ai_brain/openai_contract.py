"""Offline OpenAI Responses API wire contract; performs no network requests.

No caller may send this payload until a separately implemented execution boundary
has authorized an action and reserved sufficient budget. A result is untrusted.
"""
import json
from uuid import UUID

from pydantic import BaseModel

from app.ai_brain.contracts import research_output_schema  # noqa: F401  (re-exported)
from app.ai_brain.output_contracts import RESEARCH, OutputContract
from app.ai_brain.prompts import PromptTemplate
from app.ai_brain.providers import ProviderResult, Usage


class ProviderOutputError(ValueError):
    def __init__(self, code: str, usage: Usage | None = None, request_id: str | None = None):
        super().__init__(code)
        self.code, self.usage, self.request_id = code, usage, request_id


def validated_result(text: str, usage: Usage, request_id: str | None, known_sources: set[UUID], verified_sources: set[UUID],
                     contract: OutputContract = RESEARCH, context: dict | None = None) -> ProviderResult:
    if len(text) > 1000000:
        raise ProviderOutputError('INVALID_OUTPUT', usage, request_id)
    try:
        validated = contract.validate(json.loads(text), known_sources, verified_sources, context or {})
    except (ValueError, TypeError, RecursionError):
        raise ProviderOutputError('OUTPUT_VALIDATION_FAILED', usage, request_id) from None
    return ProviderResult(payload=validated, usage=usage, provider_request_id=request_id)


def build_request(model: str, prompt: PromptTemplate, request: BaseModel, max_output_tokens: int, contract: OutputContract = RESEARCH) -> dict:
    if not model.strip() or len(model) > 200 or not 1 <= max_output_tokens <= 100000:
        raise ValueError('Invalid model or output limit')
    return {'model': model, 'input': prompt.messages(request), 'max_output_tokens': max_output_tokens,
            'store': False, 'text': {'format': {'type': 'json_schema', 'name': contract.name, 'strict': True, 'schema': contract.schema()}}}


def parse_response(raw: object, known_sources: set[UUID], verified_sources: set[UUID], contract: OutputContract = RESEARCH, context: dict | None = None) -> ProviderResult:
    if not isinstance(raw, dict):
        raise ProviderOutputError('INVALID_RESPONSE')
    request_id = raw.get('id') if isinstance(raw.get('id'), str) and 1 <= len(raw['id']) <= 200 else None
    token_data = raw.get('usage')
    usage = None
    if isinstance(token_data, dict) and type(token_data.get('input_tokens')) is int and type(token_data.get('output_tokens')) is int:
        try:
            usage = Usage(token_data['input_tokens'], token_data['output_tokens'])
        except ValueError:
            pass
    if raw.get('status') != 'completed' or usage is None:
        raise ProviderOutputError('INCOMPLETE_OR_USAGE_UNKNOWN', usage, request_id)
    output = raw.get('output')
    if not isinstance(output, list):
        raise ProviderOutputError('INVALID_OUTPUT', usage, request_id)
    texts = []
    for item in output:
        if not isinstance(item, dict) or item.get('type') != 'message':
            continue
        content = item.get('content')
        if not isinstance(content, list):
            raise ProviderOutputError('INVALID_OUTPUT', usage, request_id)
        for part in content:
            if isinstance(part, dict) and part.get('type') == 'refusal':
                raise ProviderOutputError('PROVIDER_REFUSAL', usage, request_id)
            if isinstance(part, dict) and part.get('type') == 'output_text' and isinstance(part.get('text'), str):
                texts.append(part['text'])
    if len(texts) != 1:
        raise ProviderOutputError('INVALID_OUTPUT', usage, request_id)
    return validated_result(texts[0], usage, request_id, known_sources, verified_sources, contract, context)
