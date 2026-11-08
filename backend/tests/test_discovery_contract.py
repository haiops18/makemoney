"""Step 7B: ranking output validation and the search client (fake transport, no network)."""
import json
from uuid import uuid4

import pytest

from app.ai_brain.adapters import adapter_for
from app.ai_brain.output_contracts import OPPORTUNITY_RANKING, contract_for_prompt
from app.ai_brain.ranking_contract import RankingOutput, rank_value, ranking_output_schema, validate_ranking
from app.integrations.search import SearchFailed, search

SOURCE = uuid4()


def candidate(**extra):
    base = {'title': 'Affiliate váy nữ qua Facebook Page', 'business_model': 'AFFILIATE', 'summary': 'Đăng bài review váy và gắn link ACCESSTRADE.',
            'how_it_works': ['Chọn 10 sản phẩm', 'Đăng 2 bài mỗi ngày'], 'income_low_vnd': 500_000, 'income_base_vnd': 2_000_000, 'income_high_vnd': 6_000_000,
            'startup_cost_vnd': 0, 'monthly_cost_vnd': 200_000, 'weeks_to_first_income': 4, 'hours_per_week': 6, 'success_likelihood': 40, 'risk_level': 'MEDIUM',
            'risks': ['Tiếp cận tự nhiên thấp'], 'required_integrations': ['ACCESSTRADE', 'FACEBOOK_PAGE'],
            'scores': {key: 60 for key in ('market_demand', 'monetization_potential', 'automation_feasibility', 'experiment_cost', 'competitive_advantage', 'scalability', 'evidence_confidence')},
            'assumptions': ['Hoa hồng thời trang khoảng 3-8%'], 'source_ids': [str(SOURCE)]}
    return {**base, **extra}


def output(*items):
    return {'summary': 'So sánh các hướng', 'candidates': list(items) or [candidate()]}


def test_valid_ranking_and_expected_value():
    result = validate_ranking(output(candidate(), candidate(title='Kênh TikTok review')), {SOURCE}, set(), {})
    assert isinstance(result, RankingOutput) and len(result.candidates) == 2
    assert rank_value(result.candidates[0].model_dump()) == 800_000


@pytest.mark.parametrize('bad', [
    {'income_low_vnd': 3_000_000},  # low > base
    {'success_likelihood': 101},
    {'risk_level': 'NONE'},
    {'assumptions': []},
    {'source_ids': [str(uuid4())]},
    {'summary': 'Xem thêm tại shopee.vn/abc'},
    {'how_it_works': []},
    {'business_model': 'CASINO'},
    {'extra': 1},
])
def test_invalid_candidates_are_rejected(bad):
    with pytest.raises(ValueError):
        validate_ranking(output(candidate(**bad)), {SOURCE}, set(), {})


def test_duplicate_titles_and_too_many_candidates_are_rejected():
    with pytest.raises(ValueError):
        validate_ranking(output(candidate(), candidate(title='affiliate VÁY nữ qua facebook page')), {SOURCE}, set(), {})
    with pytest.raises(ValueError):
        validate_ranking(output(*[candidate(title=f'Ý tưởng {i}') for i in range(9)]), {SOURCE}, set(), {})


def test_contract_registry_and_strict_schema():
    assert contract_for_prompt('opportunity_ranking') is OPPORTUNITY_RANKING
    schema = ranking_output_schema()
    item = schema['properties']['candidates']['items']
    assert item['additionalProperties'] is False and set(item['required']) == set(item['properties'])
    wire = adapter_for('OPENAI', None).build('gpt-test', __import__('app.ai_brain.prompts', fromlist=['PromptTemplate']).PromptTemplate('opportunity_ranking', '1', 's', 'd'),
                                               __import__('app.ai_brain.prompts', fromlist=['ResearchRequest']).ResearchRequest(objective='x'), 500, OPPORTUNITY_RANKING)
    assert wire['text']['format']['name'] == 'opportunity_ranking' and wire['text']['format']['strict'] is True


def test_search_clients_send_the_query_to_the_official_host_only():
    calls = []

    def tavily(method, url, hosts, headers, payload, timeout, query=None):
        calls.append((method, url, hosts, headers, payload, query))
        return 200, {'results': [{'title': 'Hoa hồng Shopee', 'url': 'https://example.vn/a', 'content': 'Thời trang  nữ\n3.68%'},
                                 {'title': 'Bad', 'url': 'javascript:alert(1)', 'content': 'x'}, {'title': 'Empty', 'url': 'https://e.vn', 'content': ''}]}
    hits = search('SEARCH_TAVILY', 'tvly-1', 'váy nữ affiliate', 3, transport=tavily)
    assert [(hit.title, hit.url, hit.snippet) for hit in hits] == [('Hoa hồng Shopee', 'https://example.vn/a', 'Thời trang nữ 3.68%')]
    assert calls[0][:4] == ('POST', 'https://api.tavily.com/search', {'api.tavily.com'}, {'Authorization': 'Bearer tvly-1'}) and calls[0][4]['query'] == 'váy nữ affiliate'

    def brave(method, url, hosts, headers, payload, timeout, query=None):
        calls.append((method, url, hosts, headers, payload, query))
        return 200, {'web': {'results': [{'title': 'B', 'url': 'https://b.vn/x', 'description': 'mô tả'}]}}
    assert search('SEARCH_BRAVE', 'brv', 'q', 2, transport=brave)[0].url == 'https://b.vn/x'
    assert calls[-1][1] == 'https://api.search.brave.com/res/v1/web/search' and calls[-1][5]['q'] == 'q' and calls[-1][3]['X-Subscription-Token'] == 'brv'


@pytest.mark.parametrize('code,message', [(401, 'rejected'), (429, 'rate limiting'), (500, 'error')])
def test_search_failures_are_short_and_secret_free(code, message):
    with pytest.raises(SearchFailed) as raised:
        search('SEARCH_TAVILY', 'tvly-secret', 'q', 1, transport=lambda *a, **k: (code, {'detail': 'tvly-secret'}))
    assert message in str(raised.value) and 'tvly-secret' not in str(raised.value)
    assert json.dumps(str(raised.value))
