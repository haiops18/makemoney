"""Step 7A campaigns: Owner data, evidence status, link rules, idempotency and audit."""
from itertools import count

import pytest
from sqlalchemy import func, select

from app.campaigns.links import LinkRuleError, compose, normalize_hosts
from app.db.models import AuditEvent

_keys = count()
SCORES = {key: 80 for key in ['market_demand', 'monetization_potential', 'automation_feasibility', 'experiment_cost', 'competitive_advantage', 'scalability', 'evidence_confidence']}


def post(client, headers, path, body=None, key=None):
    return client.post(path, json=body if body is not None else {}, headers={**headers, 'Idempotency-Key': key or f'k{next(_keys)}'})


def evaluated_opportunity(client, headers, risk='LOW'):
    item = post(client, headers, '/api/v1/opportunities', {'title': 'Shopee thời trang nữ', 'business_model': 'AFFILIATE'}).json()
    result = post(client, headers, f"/api/v1/opportunities/{item['id']}/evaluate", {'scores': SCORES, 'risk_level': risk})
    assert result.status_code == 200, result.text
    return item['id']


def campaign(client, headers, **extra):
    body = {'opportunity_id': evaluated_opportunity(client, headers), 'name': 'Thời trang nữ — Facebook/Reels', 'niche': 'Thời trang nữ', 'max_cost_usd': '2', **extra}
    result = post(client, headers, '/api/v1/campaigns', body)
    assert result.status_code == 201, result.text
    return result.json()


def source(client, headers, campaign_id, verify=None):
    created = post(client, headers, f'/api/v1/campaigns/{campaign_id}/sources', {'source_name': 'GHN', 'source_url': 'https://ghn.vn/blogs/x', 'excerpt': 'Thời trang nữ 3.68%', 'captured_at': '2026-11-06T00:00:00Z'}).json()
    if verify:
        assert post(client, headers, f"/api/v1/campaigns/{campaign_id}/sources/{created['id']}/verification", {'status': verify, 'note': 'Owner checked'}).status_code == 200
    return created['id']


def program(client, headers, campaign_id, **extra):
    body = {'network': 'SHOPEE', 'name': 'Shopee Affiliate', 'link_hosts': ['s.shopee.vn', 'shope.ee'], 'tracking_param_keys': ['sub_id'], **extra}
    result = post(client, headers, f'/api/v1/campaigns/{campaign_id}/programs', body)
    assert result.status_code == 201, result.text
    return result.json()


def test_campaign_requires_owner_and_an_evaluated_opportunity(client, auth_headers):
    assert client.get('/api/v1/campaigns').status_code == 401
    draft = post(client, auth_headers, '/api/v1/opportunities', {'title': 'Draft only', 'business_model': 'AFFILIATE'}).json()
    body = {'opportunity_id': draft['id'], 'name': 'X', 'max_cost_usd': '1'}
    assert post(client, auth_headers, '/api/v1/campaigns', body).status_code == 409
    disqualified = evaluated_opportunity(client, auth_headers, risk='SEVERE')
    assert post(client, auth_headers, '/api/v1/campaigns', {**body, 'opportunity_id': disqualified}).status_code == 409
    assert post(client, auth_headers, '/api/v1/campaigns', {**body, 'opportunity_id': evaluated_opportunity(client, auth_headers), 'max_cost_usd': 1.5}).status_code == 422
    assert post(client, auth_headers, '/api/v1/campaigns', {**body, 'opportunity_id': evaluated_opportunity(client, auth_headers), 'max_cost_usd': '46'}).status_code == 422


def test_campaign_create_is_idempotent_and_audited(client, auth_headers):
    body = {'opportunity_id': evaluated_opportunity(client, auth_headers), 'name': 'Campaign', 'max_cost_usd': '2'}
    first = post(client, auth_headers, '/api/v1/campaigns', body, key='same')
    again = post(client, auth_headers, '/api/v1/campaigns', body, key='same')
    assert first.status_code == again.status_code == 201
    assert first.json()['id'] == again.json()['id']
    assert first.json()['business_model'] == 'AFFILIATE' and first.json()['status'] == 'DRAFT' and first.json()['disclosure_text'] is None
    assert post(client, auth_headers, '/api/v1/campaigns', {**body, 'name': 'Other'}, key='same').status_code == 409
    assert len(client.get('/api/v1/campaigns', headers=auth_headers).json()) == 1
    from app.db.session import get_db
    from app.main import app
    db = next(app.dependency_overrides[get_db]())
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'campaign.created')) == 1


def test_update_uses_versions_and_status_transitions(client, auth_headers):
    item = campaign(client, auth_headers)
    path = f"/api/v1/campaigns/{item['id']}"
    stale = client.patch(path, json={'version': 9, 'name': 'New'}, headers={**auth_headers, 'Idempotency-Key': 'p1'})
    assert stale.status_code == 409
    updated = client.patch(path, json={'version': 1, 'disclosure_text': 'Có link tiếp thị liên kết.'}, headers={**auth_headers, 'Idempotency-Key': 'p2'})
    assert updated.status_code == 200 and updated.json()['version'] == 2 and updated.json()['disclosure_text'] == 'Có link tiếp thị liên kết.'
    assert client.patch(path, json={'version': 2, 'name': None}, headers={**auth_headers, 'Idempotency-Key': 'p3'}).status_code == 422
    assert post(client, auth_headers, path + '/status', {'version': 2, 'status': 'PAUSED'}).status_code == 409
    assert post(client, auth_headers, path + '/status', {'version': 2, 'status': 'ACTIVE'}).json()['status'] == 'ACTIVE'
    assert post(client, auth_headers, path + '/status', {'version': 3, 'status': 'ARCHIVED'}).json()['status'] == 'ARCHIVED'
    assert post(client, auth_headers, path + '/status', {'version': 4, 'status': 'ACTIVE'}).status_code == 409
    assert post(client, auth_headers, path + '/sources', {'source_name': 'x', 'excerpt': 'y', 'captured_at': '2026-11-06T00:00:00Z'}).status_code == 409
    assert client.patch(path, json={'version': 4, 'name': 'Late'}, headers={**auth_headers, 'Idempotency-Key': 'p4'}).status_code == 409


def test_sources_are_owner_verified_once_and_never_in_the_future(client, auth_headers):
    item = campaign(client, auth_headers)
    base = f"/api/v1/campaigns/{item['id']}/sources"
    assert post(client, auth_headers, base, {'source_name': 'x', 'excerpt': 'y', 'captured_at': '2099-01-01T00:00:00Z'}).status_code == 422
    assert post(client, auth_headers, base, {'source_name': 'x', 'excerpt': 'y', 'captured_at': '2026-11-06T00:00:00'}).status_code == 422
    assert post(client, auth_headers, base, {'source_name': 'x', 'source_url': 'javascript:alert(1)', 'excerpt': 'y', 'captured_at': '2026-11-06T00:00:00Z'}).status_code == 422
    source_id = source(client, auth_headers, item['id'], verify='VERIFIED')
    assert post(client, auth_headers, f'{base}/{source_id}/verification', {'status': 'REJECTED', 'note': 'changed my mind'}).status_code == 409
    listed = client.get(base, headers=auth_headers).json()
    assert listed[0]['verification_status'] == 'VERIFIED' and listed[0]['verified_by'] == 'owner'


def test_terms_carry_their_evidence_status(client, auth_headers):
    item = campaign(client, auth_headers)
    other = campaign(client, auth_headers)
    plan = program(client, auth_headers, item['id'])
    terms = f"/api/v1/campaigns/{item['id']}/programs/{plan['id']}/terms"
    verified = source(client, auth_headers, item['id'], verify='VERIFIED')
    pending = source(client, auth_headers, item['id'])
    rejected = source(client, auth_headers, item['id'], verify='REJECTED')
    foreign = source(client, auth_headers, other['id'], verify='VERIFIED')
    rate = {'term': 'COMMISSION_RATE', 'value_text': 'Thời trang nữ 3.68%', 'value_numeric': '3.68', 'unit': 'PERCENT'}
    assert post(client, auth_headers, terms, {**rate, 'source_id': verified}).json()['evidence_status'] == 'VERIFIED'
    assert post(client, auth_headers, terms, {**rate, 'source_id': pending}).json()['evidence_status'] == 'UNVERIFIED'
    assert post(client, auth_headers, terms, {'term': 'PAYOUT', 'value_text': 'Ngày 25-30 hằng tháng'}).json()['evidence_status'] == 'UNSOURCED'
    assert post(client, auth_headers, terms, {**rate, 'source_id': rejected}).status_code == 409
    assert post(client, auth_headers, terms, {**rate, 'source_id': foreign}).status_code == 422
    assert post(client, auth_headers, terms, {**rate, 'value_numeric': '101'}).status_code == 422
    assert post(client, auth_headers, terms, {**rate, 'unit': 'NONE'}).status_code == 422
    assert post(client, auth_headers, terms, {**rate, 'value_numeric': 3.68}).status_code == 422
    assert post(client, auth_headers, f"/api/v1/campaigns/{other['id']}/programs/{plan['id']}/terms", rate).status_code == 404
    listed = client.get(f"/api/v1/campaigns/{item['id']}/programs", headers=auth_headers).json()
    # SQLite timestamps have one-second precision, so same-second terms have no fixed order here.
    assert sorted((term['term'], term['evidence_status']) for term in listed[0]['terms']) == [('COMMISSION_RATE', 'UNVERIFIED'), ('COMMISSION_RATE', 'VERIFIED'), ('PAYOUT', 'UNSOURCED')]
    assert post(client, auth_headers, f"/api/v1/campaigns/{item['id']}/programs", {'network': 'SHOPEE', 'name': 'Shopee Affiliate', 'link_hosts': ['shopee.vn']}).status_code == 409
    assert post(client, auth_headers, f"/api/v1/campaigns/{item['id']}/programs", {'network': 'SHOPEE', 'name': 'Wild', 'link_hosts': ['*.shopee.vn']}).status_code == 422


def test_products_need_a_source_for_any_price(client, auth_headers):
    item = campaign(client, auth_headers)
    base = f"/api/v1/campaigns/{item['id']}/products"
    assert post(client, auth_headers, base, {'name': 'Váy', 'price_text': '199.000đ'}).status_code == 422
    created = post(client, auth_headers, base, {'name': 'Váy', 'merchant': 'Shop A', 'price_text': '199.000đ', 'price_source_id': source(client, auth_headers, item['id'])})
    assert created.status_code == 201 and created.json()['price_evidence_status'] == 'UNVERIFIED'
    assert post(client, auth_headers, base, {'name': 'Áo'}).json()['price_evidence_status'] == 'UNSOURCED'


def test_links_follow_program_rules_and_keep_the_original(client, auth_headers):
    item = campaign(client, auth_headers)
    plan = program(client, auth_headers, item['id'])
    base = f"/api/v1/campaigns/{item['id']}/links"
    link = {'program_id': plan['id'], 'label': 'Váy', 'original_url': 'https://s.shopee.vn/AbC?x=1#top', 'tracking_params': {'sub_id': 'reels-01'}}
    created = post(client, auth_headers, base, link)
    assert created.status_code == 201, created.text
    assert created.json()['final_url'] == 'https://s.shopee.vn/AbC?x=1&sub_id=reels-01#top'
    assert post(client, auth_headers, base, link).status_code == 409
    for bad in ({'original_url': 'https://evil.example/s.shopee.vn'}, {'original_url': 'http://s.shopee.vn/x'}, {'original_url': 'https://u:p@s.shopee.vn/x'},
                {'tracking_params': {'utm_source': 'x'}}, {'tracking_params': {'sub_id': 'a b'}}, {'original_url': 'https://s.shopee.vn/x?sub_id=1'}):
        assert post(client, auth_headers, base, {**link, **bad}).status_code == 422, bad
    retired = post(client, auth_headers, f"{base}/{created.json()['id']}/retire")
    assert retired.status_code == 200 and retired.json()['status'] == 'RETIRED'
    assert post(client, auth_headers, f"{base}/{created.json()['id']}/retire").status_code == 409
    assert post(client, auth_headers, base, link).status_code == 201


def test_link_composition_rules():
    assert compose('https://shope.ee/x', ['shope.ee'], [], {}) == 'https://shope.ee/x'
    assert compose('https://vn.shopee.vn/p?', ['shopee.vn'], ['sub_id'], {'sub_id': 'a'}) == 'https://vn.shopee.vn/p?sub_id=a'
    assert compose('https://shopee.vn/p', ['shopee.vn'], ['b', 'a'], {'b': '2', 'a': '1'}) == 'https://shopee.vn/p?a=1&b=2'
    for url in ('https://notshopee.vn/x', 'https://shopee.vn.evil.io/x', 'https://shopee.vn/x y'):
        with pytest.raises(LinkRuleError):
            compose(url, ['shopee.vn'], [], {})
    with pytest.raises(LinkRuleError):
        normalize_hosts(['localhost'])
