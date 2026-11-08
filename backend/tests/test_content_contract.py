"""Step 7A content output contract and the unchanged research wire format."""
import json
from uuid import uuid4

import pytest

from app.ai_brain.adapters import adapter_for
from app.ai_brain.content_contract import ContentRequest, content_output_schema, validate_content
from app.ai_brain.openai_contract import ProviderOutputError, build_request, parse_response
from app.ai_brain.output_contracts import CONTENT_DRAFT, RESEARCH, contract_for_prompt, contract_named
from app.ai_brain.prompts import PromptTemplate, ResearchRequest

VERIFIED, UNVERIFIED = uuid4(), uuid4()
KNOWN = {VERIFIED, UNVERIFIED}
CONTEXT = {'content_types': ['SOCIAL_POST', 'SHORT_CAPTION'], 'expected_items': 2}
PROMPT = PromptTemplate('content_draft', '1', 'system', 'developer')


def item(kind='SOCIAL_POST', **extra):
    return {'content_type': kind, 'title': 'Váy hè', 'body': 'Xem tại {{AFFILIATE_LINK}}', 'hashtags': ['vay'], 'cta': 'Mua ngay',
            'claims': [{'classification': 'FACT', 'statement': 'Hoa hồng 3.68%', 'source_ids': [str(VERIFIED)]}], **extra}


def output(*items):
    return {'summary': 'Angle', 'items': list(items) or [item(), item('SHORT_CAPTION')]}


def test_valid_output_passes():
    result = validate_content(output(), KNOWN, {VERIFIED}, CONTEXT)
    assert [entry.content_type for entry in result.items] == ['SOCIAL_POST', 'SHORT_CAPTION']


@pytest.mark.parametrize('bad', [
    {'body': 'No placeholder here'},
    {'body': 'Mua ở https://s.shopee.vn/x {{AFFILIATE_LINK}}'},
    {'body': 'Vào www.example.com {{AFFILIATE_LINK}}'},
    {'body': 'Ghé shopee.vn/abc {{AFFILIATE_LINK}}'},
    {'cta': 'Click bit.ly/x'},
    {'cta': 'Xem goo.gl/abc'},
    {'body': 'youtu.be/x {{AFFILIATE_LINK}}'},
    {'body': 'Vào //evil.xyz/p {{AFFILIATE_LINK}}'},
    {'body': 'IP 1.2.3.4/x {{AFFILIATE_LINK}}'},
    {'body': 'hxxps://a {{AFFILIATE_LINK}}'},
    {'title': 'Ghé Shopee.VN'},
    {'claims': [{'classification': 'FACT', 'statement': 'x', 'source_ids': [str(UNVERIFIED)]}]},
    {'claims': [{'classification': 'FACT', 'statement': 'x', 'source_ids': [str(uuid4())]}]},
    {'claims': [{'classification': 'FACT', 'statement': 'x', 'source_ids': []}]},
    {'hashtags': ['two words']},
    {'extra': 'field'},
])
def test_invalid_items_are_rejected(bad):
    with pytest.raises(ValueError):
        validate_content(output(item(**bad), item('SHORT_CAPTION')), KNOWN, {VERIFIED}, CONTEXT)


def test_ordinary_vietnamese_text_is_not_a_web_address():
    body = 'Giao TP.HCM, giá 199.000đ, hoa hồng 3.68%, size M/L, 1/2 giá, v.v. đẹp lắm.mua ngay {{AFFILIATE_LINK}}'
    validate_content(output(item(body=body), item('SHORT_CAPTION')), KNOWN, {VERIFIED}, CONTEXT)


def test_counts_types_and_lengths_are_enforced():
    with pytest.raises(ValueError):
        validate_content(output(item()), KNOWN, {VERIFIED}, CONTEXT)
    with pytest.raises(ValueError):
        validate_content(output(item(), item('VIDEO_SCRIPT')), KNOWN, {VERIFIED}, CONTEXT)
    with pytest.raises(ValueError):
        validate_content(output(item(), item('SHORT_CAPTION', body='a' * 601 + '{{AFFILIATE_LINK}}')), KNOWN, {VERIFIED}, CONTEXT)
    with pytest.raises(ValueError):
        validate_content(output(), KNOWN, {VERIFIED}, {})
    hypothesis = item(claims=[{'classification': 'HYPOTHESIS', 'statement': 'Có thể hợp', 'source_ids': [str(UNVERIFIED)]}])
    assert validate_content(output(hypothesis, item('SHORT_CAPTION')), KNOWN, {VERIFIED}, CONTEXT)


def test_content_request_has_no_link_field():
    request = ContentRequest(language='vi', campaign_name='C', network='SHOPEE', program_name='P', content_types=['SOCIAL_POST'], count_per_type=1)
    assert request.link_placeholder == '{{AFFILIATE_LINK}}'
    assert not any('url' in name for name in ContentRequest.model_fields)
    with pytest.raises(ValueError):
        ContentRequest(language='vi', campaign_name='C', network='SHOPEE', program_name='P', content_types=['SOCIAL_POST'], count_per_type=1, affiliate_url='https://x')


def test_research_wire_format_is_unchanged():
    request = ResearchRequest(objective='Find a niche')
    prompt = PromptTemplate('research', '1', 'system', 'developer')
    wire = build_request('gpt-test', prompt, request, 800)
    assert wire == build_request('gpt-test', prompt, request, 800, RESEARCH)
    assert wire['text']['format']['name'] == 'research_output' and 'findings' in wire['text']['format']['schema']['properties']
    for kind in ('ANTHROPIC', 'GEMINI'):
        adapter = adapter_for(kind, None)
        assert adapter.build('model-test', prompt, request, 800) == adapter.build('model-test', prompt, request, 800, RESEARCH)
    assert contract_for_prompt('research_report') is RESEARCH and contract_for_prompt('content_draft') is CONTENT_DRAFT
    assert contract_named(None) is RESEARCH
    with pytest.raises(ValueError):
        contract_named('unknown')


def test_every_adapter_uses_the_content_schema_and_validator():
    request = ContentRequest(language='vi', campaign_name='C', network='SHOPEE', program_name='P', content_types=['SOCIAL_POST', 'SHORT_CAPTION'], count_per_type=1)
    openai = build_request('gpt-test', PROMPT, request, 800, CONTENT_DRAFT)
    assert openai['text']['format'] == {'type': 'json_schema', 'name': 'content_draft', 'strict': True, 'schema': content_output_schema()}
    assert json.dumps(content_output_schema(), separators=(',', ':')) in adapter_for('ANTHROPIC', None).build('claude-test', PROMPT, request, 800, CONTENT_DRAFT)['system']
    assert 'items' in adapter_for('GEMINI', None).build('gemini-test', PROMPT, request, 800, CONTENT_DRAFT)['generationConfig']['responseSchema']['properties']
    raw = {'id': 'resp-1', 'status': 'completed', 'usage': {'input_tokens': 1, 'output_tokens': 1},
           'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(output())}]}]}
    assert len(parse_response(raw, KNOWN, {VERIFIED}, CONTENT_DRAFT, CONTEXT).payload.items) == 2
    with pytest.raises(ProviderOutputError) as error:
        parse_response(raw, KNOWN, set(), CONTENT_DRAFT, CONTEXT)
    assert error.value.code == 'OUTPUT_VALIDATION_FAILED'
    with pytest.raises(ProviderOutputError):
        parse_response(raw, KNOWN, {VERIFIED})  # research contract rejects content output
