"""Step 7B discovery on PostgreSQL: fake web search, fake providers, one auto-run approval, Owner decision.

No request leaves the process. The test creates no AI provider when the pipeline suite already
configured the research roles (the Step 6 E2E on the same database depends on that state).
"""
import json
from uuid import UUID

import pytest
from sqlalchemy import func, select

import app.api.discovery_routes as discovery_routes
from app.db.models import AuditEvent, DiscoveryCandidate, Opportunity, OpportunityEvidence
from test_postgres_ai_pipeline import (HEADERS, ROLE_PROVIDER, FakeProviders, _auto_run_approval, _configure_agents, _drain, _enable_consent, _policies, _start,  # noqa: F401
                                       key, pg)

SCORES = {name: 70 for name in ('market_demand', 'monetization_potential', 'automation_feasibility', 'experiment_cost', 'competitive_advantage', 'scalability', 'evidence_confidence')}


class FakeSearch:
    def __init__(self, code=200):
        self.code, self.calls = code, []

    def __call__(self, method, url, hosts, headers, payload, timeout, query=None):
        self.calls.append((method, url, hosts, payload['query']))
        number = len(self.calls)
        return self.code, {'results': [{'title': f'Kết quả {number}-{i}', 'url': f'https://tin.example.vn/{number}/{i}', 'content': f'Hoa hồng thời trang nữ khoảng 3-8% ({number}.{i})'}
                                       for i in range(2)] + [{'title': 'Trùng', 'url': 'https://tin.example.vn/1/0', 'content': 'trùng lặp'}]}


class FakeDiscoveryProviders(FakeProviders):
    """Research stages cite a source as ESTIMATE (sources are unverified); the ranking stage ranks two ideas."""

    def text(self, request):
        if request.get('text', {}).get('format', {}).get('name') == 'opportunity_ranking':
            user = json.loads(request['input'][-1]['content'])
            source = user['evidence'][0]['source_id']
            idea = {'business_model': 'AFFILIATE', 'how_it_works': ['Chọn sản phẩm', 'Đăng bài'], 'startup_cost_vnd': 0, 'monthly_cost_vnd': 100_000,
                    'weeks_to_first_income': 4, 'hours_per_week': 6, 'risk_level': 'MEDIUM', 'risks': ['Tiếp cận thấp'], 'required_integrations': ['ACCESSTRADE', 'FACEBOOK_PAGE'],
                    'scores': SCORES, 'assumptions': ['Hoa hồng 3-8%'], 'source_ids': [source]}
            return json.dumps({'summary': 'Hai hướng affiliate', 'candidates': [
                {**idea, 'title': 'Review váy công sở', 'summary': 'Ít rủi ro', 'income_low_vnd': 300_000, 'income_base_vnd': 1_000_000, 'income_high_vnd': 3_000_000, 'success_likelihood': 50},
                {**idea, 'title': 'So sánh giày nữ', 'summary': 'Thu nhập cao hơn', 'income_low_vnd': 500_000, 'income_base_vnd': 4_000_000, 'income_high_vnd': 9_000_000, 'success_likelihood': 30}]})
        user = json.loads(request['input'][-1]['content']) if 'input' in request else None
        source = user['evidence'][0]['source_id'] if user else None
        return json.dumps({'summary': f'Stage summary {len(self.calls)}', 'findings': [
            {'classification': 'ESTIMATE', 'statement': 'Nhu cầu ổn định', 'source_ids': [source] if source else [], 'assumptions': ['Theo kết quả tìm kiếm']}]})


def _research_profiles(client):
    """Reuse the research-role providers when present (re-storing their keys); otherwise configure them once."""
    agents = {item['id']: item['role'] for item in client.get('/api/v1/agents', headers=HEADERS).json()}
    profiles = {agents[item['agent_id']]: item for item in client.get('/api/v1/ai/agent-profiles', headers=HEADERS).json() if item['agent_id'] in agents}
    providers = {item['id']: item for item in client.get('/api/v1/ai/providers', params={'limit': 100}, headers=HEADERS).json()}
    if not all(role in profiles and profiles[role]['enabled'] and profiles[role]['provider_id'] in providers for role in ROLE_PROVIDER):
        _configure_agents(client)
        return
    for role in ROLE_PROVIDER:
        provider = providers[profiles[role]['provider_id']]
        assert client.patch(f"/api/v1/ai/providers/{provider['id']}", json={'api_key': f"{provider['kind'].lower()}-secret"}, headers=key()).status_code == 200


def _search_integration(client):
    created = client.post('/api/v1/integrations', json={'kind': 'SEARCH_TAVILY', 'label': f'Tavily {key()["Idempotency-Key"][:8]}', 'secret': 'tvly-test-secret'}, headers=key())
    assert created.status_code == 201, created.text
    return created.json()['id']


def _archive(client, integration_id):
    assert client.post(f'/api/v1/integrations/{integration_id}/archive', headers=key()).status_code == 200


@pytest.mark.postgres
def test_discovery_searches_ranks_and_owner_approval_creates_an_evaluated_opportunity(pg, monkeypatch):
    client, factory = pg
    internal, ai = _policies(client)
    _enable_consent(client, ai)
    _research_profiles(client)
    integration = _search_integration(client)
    try:
        search = FakeSearch()
        monkeypatch.setattr(discovery_routes, 'search_transport', search)
        request_key = key()
        body = {'topic': 'thời trang nữ', 'query_count': 2, 'results_per_query': 3, 'max_cost_usd': '2'}
        created = client.post('/api/v1/discovery', json=body, headers=request_key)
        assert created.status_code == 201, created.text
        discovery = created.json()
        assert [call[3] for call in search.calls] == ['thời trang nữ kiếm tiền online Việt Nam', 'thời trang nữ tiếp thị liên kết hoa hồng']
        assert all(call[1] == 'https://api.tavily.com/search' and call[2] == {'api.tavily.com'} for call in search.calls)
        assert discovery['source_count'] == 4 and all(s['verification_status'] == 'UNVERIFIED' for s in discovery['sources']) and discovery['workflow_status'] == 'DRAFT'
        assert 'tvly-test-secret' not in created.text
        # A replay returns the stored result without searching again.
        assert client.post('/api/v1/discovery', json=body, headers=request_key).json() == discovery and len(search.calls) == 2
        # Discovery runs stay out of the research list.
        assert all(item['id'] != discovery['run_id'] for item in client.get('/api/v1/ai/research', params={'limit': 100}, headers=HEADERS).json())

        base = _start(client, factory, discovery['workflow_id'], internal)
        prepared, approval_id = _auto_run_approval(client, base, internal, ai)
        assert prepared['summary']['ai_task_count'] == 8
        started = client.post(base + '/auto-run', json={'ai_policy_id': ai, 'internal_policy_id': internal, 'approval_id': approval_id}, headers=key())
        assert started.status_code == 201, started.text
        transport = FakeDiscoveryProviders('unused')
        _drain(factory, transport, rounds=80)
        tasks = client.get(base + '/tasks', headers=HEADERS).json()
        assert all(task['status'] == 'SUCCEEDED' for task in tasks), [(t['task_type'], t['status']) for t in tasks]
        assert len(transport.calls) == 8

        detail = client.get(f"/api/v1/discovery/{discovery['run_id']}", headers=HEADERS).json()
        assert detail['ranking_summary'] == 'Hai hướng affiliate'
        assert [(c['title'], c['rank_value'], c['status']) for c in detail['candidates']] == [('So sánh giày nữ', 1_200_000, 'PROPOSED'), ('Review váy công sở', 500_000, 'PROPOSED')]
        top, second = detail['candidates']
        path = f"/api/v1/discovery/{discovery['run_id']}/candidates"
        approved = client.post(f"{path}/{top['id']}/approve", json={'note': 'Thử 1 tháng'}, headers=key())
        assert approved.status_code == 200, approved.text
        assert approved.json()['status'] == 'APPROVED' and approved.json()['decided_by'] == 'owner'
        assert client.post(f"{path}/{top['id']}/approve", json={'note': 'again'}, headers=key()).status_code == 409
        assert client.post(f"{path}/{second['id']}/reject", json={'note': 'Không hợp'}, headers=key()).json()['status'] == 'REJECTED'
        with factory() as db:
            opportunity = db.get(Opportunity, UUID(approved.json()['opportunity_id']))
            assert opportunity.status == 'EVALUATED' and opportunity.score == 70 and opportunity.data_origin == 'AI_DISCOVERY' and opportunity.business_model == 'AFFILIATE'
            assert 'Thu nhập ước tính/tháng: 500.000đ – 9.000.000đ' in opportunity.description
            assert db.scalar(select(func.count()).select_from(OpportunityEvidence).where(OpportunityEvidence.opportunity_id == opportunity.id)) == 1
            actions = set(db.scalars(select(AuditEvent.action).where(AuditEvent.action.like('discovery.%'))))
            assert {'discovery.created', 'discovery.candidate_proposed', 'discovery.candidate_approved', 'discovery.candidate_rejected'} <= actions
            assert db.scalar(select(func.count()).select_from(DiscoveryCandidate).where(DiscoveryCandidate.run_id == UUID(discovery['run_id']))) == 2
        # The approved opportunity can start an affiliate campaign right away.
        campaign = client.post('/api/v1/campaigns', json={'opportunity_id': approved.json()['opportunity_id'], 'name': 'Giày nữ', 'max_cost_usd': '2'}, headers=key())
        assert campaign.status_code == 201, campaign.text
    finally:
        _archive(client, integration)


@pytest.mark.postgres
def test_discovery_requires_a_search_source_and_stores_nothing_when_search_fails(pg, monkeypatch):
    client, factory = pg
    _research_profiles(client)
    assert client.post('/api/v1/discovery', json={'topic': 'mỹ phẩm', 'search_kind': 'SEARCH_BRAVE'}, headers=key()).status_code == 409
    integration = _search_integration(client)
    try:
        before = len(client.get('/api/v1/discovery', headers=HEADERS).json())
        rejected = FakeSearch(code=401)
        monkeypatch.setattr(discovery_routes, 'search_transport', rejected)
        failed = client.post('/api/v1/discovery', json={'topic': 'mỹ phẩm', 'query_count': 3}, headers=key())
        assert failed.status_code == 502 and 'rejected' in failed.json()['detail'] and 'tvly' not in failed.text
        assert len(rejected.calls) == 1  # a rejected token stops further paid queries
        assert len(client.get('/api/v1/discovery', headers=HEADERS).json()) == before
        assert client.post('/api/v1/discovery', json={'topic': 'mỹ phẩm', 'max_cost_usd': '11'}, headers=key()).status_code == 422
    finally:
        _archive(client, integration)
