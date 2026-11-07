"""Verified provider adapters for fixed official endpoints.

An adapter only translates the server-built request into one provider's
wire format and validates the untrusted response. It never authorizes a call.
Saved custom base URLs (including OPENAI_COMPATIBLE) are not admitted: only the
official endpoint for each kind can receive a credential.
"""
import json
import re
from dataclasses import dataclass
from typing import Callable
from uuid import UUID

from pydantic import BaseModel

from app.ai_brain.openai_contract import ProviderOutputError, build_request as openai_build_request
from app.ai_brain.openai_contract import parse_response as openai_parse_response
from app.ai_brain.openai_contract import validated_result
from app.ai_brain.output_contracts import RESEARCH, OutputContract
from app.ai_brain.prompts import PromptTemplate
from app.ai_brain.providers import ProviderResult, Usage

_MODEL_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._\-]{0,199}$')
ANTHROPIC_VERSION = '2023-06-01'


def _request_id(value: object) -> str | None:
    return value if isinstance(value, str) and 1 <= len(value) <= 200 else None


def _schema_instruction(contract: OutputContract) -> str:
    return ('Return exactly one JSON object and nothing else. It must match this JSON schema: '
            + json.dumps(contract.schema(), separators=(',', ':')))


def _anthropic_build(model: str, prompt: PromptTemplate, request: BaseModel, max_output_tokens: int, contract: OutputContract = RESEARCH) -> dict:
    if not _MODEL_ID.match(model) or not 1 <= max_output_tokens <= 100000:
        raise ValueError('Invalid model or output limit')
    system, developer, user = prompt.messages(request)
    # Trusted instructions stay in the system field; untrusted evidence remains user content.
    return {'model': model, 'max_tokens': max_output_tokens,
            'system': f"{system['content']}\n\n{developer['content']}\n\n{_schema_instruction(contract)}",
            'messages': [{'role': 'user', 'content': user['content']}]}


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    match = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', stripped, flags=re.DOTALL)
    return match.group(1) if match else stripped


def _anthropic_parse(raw: object, known: set[UUID], verified: set[UUID], contract: OutputContract = RESEARCH, context: dict | None = None) -> ProviderResult:
    if not isinstance(raw, dict):
        raise ProviderOutputError('INVALID_RESPONSE')
    request_id = _request_id(raw.get('id'))
    data = raw.get('usage')
    usage = None
    if isinstance(data, dict) and type(data.get('input_tokens')) is int and type(data.get('output_tokens')) is int:
        cached = [data.get(name) for name in ('cache_creation_input_tokens', 'cache_read_input_tokens')]
        if all(value is None or type(value) is int for value in cached):
            try:
                usage = Usage(data['input_tokens'] + sum(value or 0 for value in cached), data['output_tokens'])
            except ValueError:
                usage = None
    if usage is None:
        raise ProviderOutputError('INCOMPLETE_OR_USAGE_UNKNOWN', None, request_id)
    if raw.get('stop_reason') == 'refusal':
        raise ProviderOutputError('PROVIDER_REFUSAL', usage, request_id)
    if raw.get('type') != 'message' or raw.get('stop_reason') != 'end_turn':
        raise ProviderOutputError('INCOMPLETE_OR_USAGE_UNKNOWN', usage, request_id)
    content = raw.get('content')
    if not isinstance(content, list):
        raise ProviderOutputError('INVALID_OUTPUT', usage, request_id)
    texts = [part['text'] for part in content if isinstance(part, dict) and part.get('type') == 'text' and isinstance(part.get('text'), str)]
    if len(texts) != 1 or any(isinstance(part, dict) and part.get('type') == 'tool_use' for part in content):
        raise ProviderOutputError('INVALID_OUTPUT', usage, request_id)
    return validated_result(_strip_fence(texts[0]), usage, request_id, known, verified, contract, context)


def _gemini_schema(node: object) -> object:
    """Gemini's response schema is an OpenAPI subset without additionalProperties."""
    if isinstance(node, dict):
        return {key: _gemini_schema(value) for key, value in node.items() if key != 'additionalProperties'}
    if isinstance(node, list):
        return [_gemini_schema(value) for value in node]
    return node


def _gemini_build(model: str, prompt: PromptTemplate, request: BaseModel, max_output_tokens: int, contract: OutputContract = RESEARCH) -> dict:
    if not _MODEL_ID.match(model) or not 1 <= max_output_tokens <= 100000:
        raise ValueError('Invalid model or output limit')
    system, developer, user = prompt.messages(request)
    return {'systemInstruction': {'parts': [{'text': system['content']}, {'text': developer['content']}]},
            'contents': [{'role': 'user', 'parts': [{'text': user['content']}]}],
            'generationConfig': {'maxOutputTokens': max_output_tokens, 'responseMimeType': 'application/json',
                                 'responseSchema': _gemini_schema(contract.schema())}}


def _gemini_parse(raw: object, known: set[UUID], verified: set[UUID], contract: OutputContract = RESEARCH, context: dict | None = None) -> ProviderResult:
    if not isinstance(raw, dict):
        raise ProviderOutputError('INVALID_RESPONSE')
    request_id = _request_id(raw.get('responseId'))
    data = raw.get('usageMetadata')
    usage = None
    if isinstance(data, dict) and type(data.get('promptTokenCount')) is int:
        extra_input = data.get('toolUsePromptTokenCount')
        output = data.get('candidatesTokenCount', 0)
        thoughts = data.get('thoughtsTokenCount', 0)
        if all(type(value) is int for value in (output, thoughts)) and (extra_input is None or type(extra_input) is int):
            try:
                # Thinking tokens are billed as output; never under-count them.
                usage = Usage(data['promptTokenCount'] + (extra_input or 0), output + thoughts)
            except ValueError:
                usage = None
    if usage is None:
        raise ProviderOutputError('INCOMPLETE_OR_USAGE_UNKNOWN', None, request_id)
    feedback = raw.get('promptFeedback')
    if isinstance(feedback, dict) and feedback.get('blockReason'):
        raise ProviderOutputError('PROVIDER_REFUSAL', usage, request_id)
    candidates = raw.get('candidates')
    if not isinstance(candidates, list) or len(candidates) != 1 or not isinstance(candidates[0], dict):
        raise ProviderOutputError('INVALID_OUTPUT', usage, request_id)
    reason = candidates[0].get('finishReason')
    if reason in {'SAFETY', 'RECITATION', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII'}:
        raise ProviderOutputError('PROVIDER_REFUSAL', usage, request_id)
    if reason != 'STOP':
        raise ProviderOutputError('INCOMPLETE_OR_USAGE_UNKNOWN', usage, request_id)
    content = candidates[0].get('content')
    parts = content.get('parts') if isinstance(content, dict) else None
    if not isinstance(parts, list):
        raise ProviderOutputError('INVALID_OUTPUT', usage, request_id)
    texts = [part['text'] for part in parts if isinstance(part, dict) and isinstance(part.get('text'), str) and not part.get('thought')]
    if len(texts) != 1:
        raise ProviderOutputError('INVALID_OUTPUT', usage, request_id)
    return validated_result(texts[0], usage, request_id, known, verified, contract, context)


def _model_ids(kind: str, raw: object) -> set[str] | None:
    if not isinstance(raw, dict):
        return None
    items = raw.get('models' if kind == 'GEMINI' else 'data')
    if not isinstance(items, list):
        return None
    names = set()
    for item in items[:5000]:
        value = item.get('name' if kind == 'GEMINI' else 'id') if isinstance(item, dict) else None
        if isinstance(value, str) and len(value) <= 300:
            names.add(value.removeprefix('models/') if kind == 'GEMINI' else value)
    return names


@dataclass(frozen=True)
class ProviderAdapter:
    kind: str
    host: str
    official_bases: tuple[str, ...]
    build: Callable[..., dict]
    parse: Callable[..., ProviderResult]

    def accepts(self, base_url: str | None) -> bool:
        return base_url is None or base_url.rstrip('/') in self.official_bases

    def inference_url(self, model: str) -> str:
        if self.kind == 'OPENAI':
            return 'https://api.openai.com/v1/responses'
        if self.kind == 'ANTHROPIC':
            return 'https://api.anthropic.com/v1/messages'
        if not _MODEL_ID.match(model):
            raise ValueError('Invalid model identifier')
        return f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'

    def models_url(self) -> str:
        return {'OPENAI': 'https://api.openai.com/v1/models', 'ANTHROPIC': 'https://api.anthropic.com/v1/models',
                'GEMINI': 'https://generativelanguage.googleapis.com/v1beta/models'}[self.kind]

    def headers(self, credential: str) -> dict[str, str]:
        if self.kind == 'OPENAI':
            return {'Authorization': f'Bearer {credential}'}
        if self.kind == 'ANTHROPIC':
            return {'x-api-key': credential, 'anthropic-version': ANTHROPIC_VERSION}
        return {'x-goog-api-key': credential}

    def model_ids(self, raw: object) -> set[str] | None:
        return _model_ids(self.kind, raw)

    def model_listed(self, raw: object, model: str) -> bool | None:
        """True/False only when the answer is certain; None if more pages exist."""
        names = _model_ids(self.kind, raw)
        if names is None:
            return None
        if model in names:
            return True
        more = raw.get('nextPageToken') if self.kind == 'GEMINI' else raw.get('has_more')
        return None if more else False


ADAPTERS = {
    'OPENAI': ProviderAdapter('OPENAI', 'api.openai.com', ('https://api.openai.com/v1',), openai_build_request, openai_parse_response),
    'ANTHROPIC': ProviderAdapter('ANTHROPIC', 'api.anthropic.com', ('https://api.anthropic.com', 'https://api.anthropic.com/v1'), _anthropic_build, _anthropic_parse),
    'GEMINI': ProviderAdapter('GEMINI', 'generativelanguage.googleapis.com',
                              ('https://generativelanguage.googleapis.com', 'https://generativelanguage.googleapis.com/v1beta'), _gemini_build, _gemini_parse),
}


def adapter_for(kind: str, base_url: str | None) -> ProviderAdapter | None:
    """Return a verified adapter, or None so callers fail closed."""
    adapter = ADAPTERS.get(kind)
    return adapter if adapter is not None and adapter.accepts(base_url) else None
