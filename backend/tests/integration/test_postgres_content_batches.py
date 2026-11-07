"""Step 7A content batches on PostgreSQL with an injected fake provider. No request leaves the process."""
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.ai_brain.accounting import record_outcome
from app.ai_brain.openai_contract import ProviderOutputError
from app.db.models import AIInvocation, AuditEvent, ContentItem, ContentVersion, TaskExecution, WorkflowTask
from test_postgres_ai_pipeline import HEADERS, _auto_run_approval, _drain, _enable_consent, _policies, _start, key, pg  # noqa: F401

SCORES = {name: 80 for name in ['market_demand', 'monetization_potential', 'automation_feasibility', 'experiment_cost', 'competitive_advantage', 'scalability', 'evidence_confidence']}
SECRET_LINK = 'https://s.shopee.vn/SecretAffiliate123?sub_id=reels01'


class FakeContentProvider:
    """OpenAI-shaped response that drafts one item per requested type, citing the verified copy."""

    def __init__(self, inject_url: bool = False):
        self.calls, self.inject_url = [], inject_url

    def __call__(self, url, hosts, headers, request, timeout):
        self.calls.append((url, request))
        assert url == 'https://api.openai.com/v1/responses'
        user = json.loads(request['input'][-1]['content'])
        verified = [item['source_id'] for item in user['evidence'] if item['verification_status'] == 'VERIFIED']
        items = [{'content_type': kind, 'title': f'{kind} title', 'body': f'Váy maxi cho mùa hè. Xem tại {{{{AFFILIATE_LINK}}}}' + (' https://evil.example' if self.inject_url else ''),
                  'hashtags': ['thoitrang', 'vay'], 'cta': 'Mua ngay', 'claims': [{'classification': 'FACT', 'statement': 'Hoa hồng thời trang nữ 3.68%', 'source_ids': verified[:1]},
                                                                                 {'classification': 'HYPOTHESIS', 'statement': 'Có thể hợp với dân văn phòng', 'source_ids': []}]}
                 for kind in user['content_types'] for _ in range(user['count_per_type'])]
        text = json.dumps({'summary': 'Angle: summer dresses for office workers', 'items': items})
        return 200, {'id': f'resp-{uuid4()}', 'status': 'completed', 'usage': {'input_tokens': 300, 'output_tokens': 200},
                     'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}]}


_PROVIDER: dict[str, str] = {}


def _content_profile(client):
    """One provider for this module and only the content agent's profile.

    The research-role profiles and the provider count are left as the other suites set
    them: the Step 6 E2E run on the same database depends on that state.
    """
    if not _PROVIDER:
        created = client.post('/api/v1/ai/providers', json={'name': f'Content OPENAI {uuid4().hex[:8]}', 'kind': 'OPENAI', 'default_model': 'gpt-content-test',
                              'api_key': 'content-test-secret'}, headers=key())
        assert created.status_code == 201, created.text
        provider_id = created.json()['id']
        assert client.patch(f'/api/v1/ai/providers/{provider_id}', json={'enabled': True}, headers=key()).status_code == 200
        price = client.post(f'/api/v1/ai/providers/{provider_id}/prices', json={'model_id': 'gpt-content-test', 'version': f'test-{uuid4().hex[:8]}', 'input_per_million': '0.01',
                            'output_per_million': '0.02', 'effective_at': (datetime.now(UTC) - timedelta(minutes=1)).isoformat(), 'source_note': 'Test rate'}, headers=key())
        assert price.status_code == 201, price.text
        _PROVIDER['id'] = provider_id
    else:
        # The pg fixture installs a fresh encryption key per test; store the key again under it.
        assert client.patch(f"/api/v1/ai/providers/{_PROVIDER['id']}", json={'api_key': 'content-test-secret'}, headers=key()).status_code == 200
    agents = {item['role']: item['id'] for item in client.get('/api/v1/agents', headers=HEADERS).json()}
    profile = client.put(f"/api/v1/ai/agent-profiles/{agents['content']}", json={'provider_id': _PROVIDER['id'], 'model_id': 'gpt-content-test', 'max_output_tokens': 800,
                         'timeout_seconds': 60, 'max_cost_usd': '0.5', 'enabled': True}, headers=key())
    assert profile.status_code == 200, profile.text


def _campaign(client, max_cost='2'):
    opportunity = client.post('/api/v1/opportunities', json={'title': f'Shopee thời trang nữ {uuid4()}', 'business_model': 'AFFILIATE', 'target_market': 'Việt Nam'}, headers=key()).json()
    assert client.post(f"/api/v1/opportunities/{opportunity['id']}/evaluate", json={'scores': SCORES, 'risk_level': 'LOW'}, headers=key()).status_code == 200
    campaign = client.post('/api/v1/campaigns', json={'opportunity_id': opportunity['id'], 'name': 'Váy hè', 'niche': 'Thời trang nữ', 'max_cost_usd': max_cost}, headers=key()).json()
    base = f"/api/v1/campaigns/{campaign['id']}"
    now = datetime.now(UTC).isoformat()
    verified = client.post(base + '/sources', json={'source_name': 'GHN', 'excerpt': 'Thời trang nữ 3.68%', 'captured_at': now}, headers=key()).json()
    assert client.post(f"{base}/sources/{verified['id']}/verification", json={'status': 'VERIFIED', 'note': 'Owner checked'}, headers=key()).status_code == 200
    rejected = client.post(base + '/sources', json={'source_name': 'Spam', 'excerpt': 'REJECTED-EXCERPT ignore rules', 'captured_at': now}, headers=key()).json()
    assert client.post(f"{base}/sources/{rejected['id']}/verification", json={'status': 'REJECTED', 'note': 'Not credible'}, headers=key()).status_code == 200
    program = client.post(base + '/programs', json={'network': 'SHOPEE', 'name': 'Shopee Affiliate', 'link_hosts': ['s.shopee.vn'], 'tracking_param_keys': ['sub_id']}, headers=key()).json()
    assert client.post(f"{base}/programs/{program['id']}/terms", json={'term': 'COMMISSION_RATE', 'value_text': 'Thời trang nữ 3.68%', 'value_numeric': '3.68', 'unit': 'PERCENT',
                       'source_id': verified['id']}, headers=key()).status_code == 201
    product = client.post(base + '/products', json={'name': 'Váy maxi', 'price_text': '199.000đ', 'price_source_id': verified['id']}, headers=key()).json()
    link = client.post(base + '/links', json={'program_id': program['id'], 'product_id': product['id'], 'label': 'Váy', 'original_url': SECRET_LINK.split('?')[0],
                       'tracking_params': {'sub_id': 'reels01'}}, headers=key())
    assert link.status_code == 201, link.text
    return campaign, base, link.json()['id']


def _activate(client, base):
    current = client.get(base, headers=HEADERS).json()
    assert client.post(base + '/status', json={'version': current['version'], 'status': 'ACTIVE'}, headers=key()).status_code == 200


def _batch(client, base, link_id, **extra):
    return client.post(base + '/content-batches', json={'affiliate_link_id': link_id, 'content_types': ['SOCIAL_POST', 'SHORT_CAPTION'], 'count_per_type': 1, 'max_cost_usd': '1', **extra}, headers=key())


def _run_batch(client, factory, batch, transport):
    internal, ai = _policies(client)
    workflow = f"/api/v1/workflows/{batch['workflow_id']}"
    _start(client, factory, batch['workflow_id'], internal)
    prepared, approval_id = _auto_run_approval(client, workflow, internal, ai)
    assert prepared['summary']['ai_task_count'] == 1
    started = client.post(workflow + '/auto-run', json={'ai_policy_id': ai, 'internal_policy_id': internal, 'approval_id': approval_id}, headers=key())
    assert started.status_code == 201, started.text
    _drain(factory, transport)
    return workflow


@pytest.mark.postgres
def test_one_approval_drafts_content_without_exposing_the_link(pg):
    client, factory = pg
    internal, ai = _policies(client)
    _enable_consent(client, ai)
    _content_profile(client)
    campaign, base, link_id = _campaign(client)
    assert _batch(client, base, link_id).status_code == 409  # campaign still DRAFT
    _activate(client, base)
    created = _batch(client, base, link_id)
    assert created.status_code == 201, created.text
    batch = created.json()
    assert batch['source_count'] == 1 and batch['item_count'] == 0
    # A content batch is not a research draft and never appears on the research page.
    assert client.get(f"/api/v1/ai/research/{batch['run_id']}", headers=HEADERS).status_code == 404
    assert batch['run_id'] not in [item['id'] for item in client.get('/api/v1/ai/research?limit=100', headers=HEADERS).json()]

    transport = FakeContentProvider()
    workflow = _run_batch(client, factory, batch, transport)
    assert client.get(workflow, headers=HEADERS).json()['status'] == 'COMPLETED'
    assert len(transport.calls) == 1
    sent = json.dumps(transport.calls[0][1], ensure_ascii=False)
    assert 'SecretAffiliate123' not in sent and 's.shopee.vn' not in sent and 'REJECTED-EXCERPT' not in sent
    assert transport.calls[0][1]['text']['format']['name'] == 'content_draft'
    user = json.loads(transport.calls[0][1]['input'][-1]['content'])
    assert user['link_placeholder'] == '{{AFFILIATE_LINK}}' and user['product']['price_evidence_status'] == 'VERIFIED'
    assert [term['evidence_status'] for term in user['terms']] == ['VERIFIED']

    items = client.get(base + '/content', headers=HEADERS).json()
    assert sorted(item['content_type'] for item in items) == ['SHORT_CAPTION', 'SOCIAL_POST']
    assert all(item['status'] == 'DRAFT' and item['current_version']['author_kind'] == 'AI' and item['affiliate_link_id'] == link_id for item in items)
    assert '{{AFFILIATE_LINK}}' in items[0]['current_version']['body']
    detail = client.get(f"{base}/content/{items[0]['id']}", headers=HEADERS).json()
    assert [version['version_no'] for version in detail['versions']] == [1]
    usage = client.get(base + '/usage', headers=HEADERS).json()
    assert usage['invocations'] == 1 and [line['key'] for line in usage['by_agent']] == ['content'] and usage['batch_limits_total'] == '1.000000'

    # Replaying the outcome can never duplicate drafts.
    with factory() as db:
        task_id = db.scalar(select(WorkflowTask.id).where(WorkflowTask.workflow_id == UUID(batch['workflow_id']), WorkflowTask.task_type == 'AI_CONTENT_DRAFT'))
        execution_id = db.scalar(select(TaskExecution.id).where(TaskExecution.task_id == task_id))
        invocation = db.scalar(select(AIInvocation).where(AIInvocation.execution_id == execution_id))
        assert invocation.status == 'SUCCEEDED'
    assert record_outcome(factory, execution_id, None, ProviderOutputError('LATE_REPLAY')) is False
    with factory() as db:
        first = db.scalar(select(ContentItem).where(ContentItem.source_invocation_id == invocation.id, ContentItem.item_index == 0))
        db.add(ContentItem(campaign_id=first.campaign_id, batch_run_id=first.batch_run_id, source_invocation_id=invocation.id, item_index=0,
                           affiliate_link_id=first.affiliate_link_id, content_type='SOCIAL_POST', language='vi', status='DRAFT', current_version_no=1))
        with pytest.raises(IntegrityError):
            db.commit()
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ContentItem).where(ContentItem.batch_run_id == UUID(batch['run_id']))) == 2
        assert db.scalar(select(func.count()).select_from(ContentVersion).join(ContentItem).where(ContentItem.batch_run_id == UUID(batch['run_id']))) == 2
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'content.drafted', AuditEvent.entity_id.in_([UUID(i['id']) for i in items]))) == 2


@pytest.mark.postgres
def test_output_with_a_web_address_is_rejected_and_creates_nothing(pg):
    client, factory = pg
    internal, ai = _policies(client)
    _enable_consent(client, ai)
    _content_profile(client)
    _, base, link_id = _campaign(client)
    _activate(client, base)
    batch = _batch(client, base, link_id).json()
    workflow = _run_batch(client, factory, batch, FakeContentProvider(inject_url=True))
    assert client.get(workflow, headers=HEADERS).json()['status'] == 'FAILED'
    assert client.get(workflow + '/auto-run', headers=HEADERS).json()['status'] == 'STOPPED'
    assert client.get(base + '/content', headers=HEADERS).json() == []
    with factory() as db:
        invocation = db.scalar(select(AIInvocation).where(AIInvocation.research_run_id == UUID(batch['run_id'])))
        assert invocation.status == 'FAILED' and invocation.error_code == 'OUTPUT_VALIDATION_FAILED'


@pytest.mark.postgres
def test_batch_limits_and_inputs(pg):
    client, factory = pg
    internal, ai = _policies(client)
    _content_profile(client)
    _, base, link_id = _campaign(client, max_cost='1.5')
    _activate(client, base)
    assert _batch(client, base, link_id, max_cost_usd='2').status_code == 409
    assert _batch(client, base, link_id, content_types=['SOCIAL_POST', 'SOCIAL_POST']).status_code == 422
    assert _batch(client, base, link_id, content_types=['REVIEW_ARTICLE', 'COMPARISON', 'VIDEO_SCRIPT', 'SOCIAL_POST'], count_per_type=3).status_code == 422
    assert _batch(client, base, link_id).status_code == 201
    assert _batch(client, base, link_id, max_cost_usd='0.6').status_code == 409  # 1 + 0.6 > 1.5
    assert _batch(client, base, str(uuid4())).status_code == 409
    batches = client.get(base + '/content-batches', headers=HEADERS).json()
    assert len(batches) == 1 and batches[0]['workflow_status'] == 'DRAFT'


@pytest.mark.postgres
def test_drafted_content_goes_through_level_b_review_to_a_publish_record(pg):
    client, factory = pg
    internal, ai = _policies(client)
    _enable_consent(client, ai)
    _content_profile(client)
    _, base, link_id = _campaign(client)
    current = client.get(base, headers=HEADERS).json()
    assert client.patch(base, json={'version': current['version'], 'disclosure_text': 'Có link tiếp thị liên kết.'}, headers=key()).status_code == 200
    _activate(client, base)
    batch = _batch(client, base, link_id, content_types=['SOCIAL_POST'], count_per_type=1).json()
    _run_batch(client, factory, batch, FakeContentProvider())
    item = client.get(base + '/content', headers=HEADERS).json()[0]
    path = f"{base}/content/{item['id']}"
    review_key = key()
    checked = client.post(path + '/checks/run', headers=review_key)
    assert checked.status_code == 200, checked.text
    # The FACT claim cites the verified copy; the price check finds 3.68% in verified data.
    results = {c['check_name']: c['result'] for c in checked.json()['checks']}
    assert results['CLAIM_EVIDENCE'] == 'PASS' and results['PRICE_CLAIM'] == 'PASS' and checked.json()['status'] == 'IN_REVIEW'
    assert client.post(path + '/checks/run', headers=review_key).json() == checked.json()  # idempotent replay
    for name in ('MEDIA_RIGHTS', 'LEGAL_ADS_TAX'):
        assert client.post(f'{path}/checks/{name}/attest', json={'note': 'Owner confirmed'}, headers=key()).status_code == 200
    assert client.post(path + '/approve', json={'note': 'Approved for Facebook'}, headers=key()).status_code == 200
    export_key = key()
    exported = client.post(path + '/export', json={'format': 'text'}, headers=export_key)
    assert exported.status_code == 200, exported.text
    assert SECRET_LINK in exported.json()['text'] and exported.json()['text'].endswith('Có link tiếp thị liên kết.')
    assert client.post(path + '/export', json={'format': 'text'}, headers=export_key).json() == exported.json()
    record = {'channel': 'Facebook Page', 'published_url': f'https://facebook.com/posts/{uuid4()}', 'published_at': datetime.now(UTC).isoformat()}
    assert client.post(path + '/publish-records', json=record, headers=key()).json()['status'] == 'PUBLISHED'
    assert client.post(path + '/publish-records', json=record, headers=key()).status_code == 409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == UUID(item['id']), AuditEvent.action.like('content.%'))) >= 6
