"""Step 7B PR-C: ACCESSTRADE import (fake transport), standing attestations and proposals."""
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select

import app.api.autopilot_routes as autopilot_routes
from app.core.config import get_settings
from app.db.models import AuditEvent, CampaignProduct, CampaignSource
from app.db.session import get_db
from app.integrations import accesstrade
from app.main import app
from test_campaigns import campaign, post
from test_content_review import _seed

AT_KEY = 'at-secret-key'


@pytest.fixture(autouse=True)
def credential_key(monkeypatch):
    monkeypatch.setattr(get_settings(), 'ai_credentials_key', SecretStr(Fernet.generate_key().decode()))


class FakeAccesstrade:
    def __init__(self, approved=True):
        self.calls, self.approved = [], approved

    def __call__(self, method, url, hosts, headers, payload, timeout, query=None):
        assert hosts == {'api.accesstrade.vn'} and headers['Authorization'] == f'Token {AT_KEY}'
        self.calls.append((method, url, payload, query))
        if url.endswith('/datafeeds'):
            return 200, {'total': 3, 'data': [
                {'product_id': 'p1', 'name': 'Váy maxi  hoa', 'url': 'https://shopee.vn/vay-1', 'merchant': 'shopee', 'price': 299000, 'discount': 199000, 'image': 'https://cf.shopee.vn/a.jpg'},
                {'product_id': 'p2', 'name': 'Bad', 'url': 'javascript:alert(1)'},
                {'product_id': 'p3', 'name': 'Áo sơ mi', 'url': 'https://shopee.vn/ao-3', 'price': '159000.0'}]}
        if url.endswith('/campaigns'):
            return 200, {'data': [{'id': '4751584435713464237', 'merchant': 'shopee' if self.approved else 'lazada', 'name': 'Shopee' if self.approved else 'Lazada'}]}
        if url.endswith('/product_link/create'):
            return 200, {'success': True, 'data': {'error_link': [], 'suspend_url': [], 'success_link': [
                {'url_origin': origin, 'short_link': f'https://shorten.asia/{index}abc', 'aff_link': 'https://go.isclix.com/deep_link/1'} for index, origin in enumerate(payload['urls'])]}}
        raise AssertionError(url)


def _connect(client, headers):
    assert post(client, headers, '/api/v1/integrations', {'kind': 'ACCESSTRADE', 'label': 'AT', 'secret': AT_KEY}).status_code == 201


def test_client_parses_and_sanitizes_products():
    products = accesstrade.list_products(AT_KEY, 'shopee', 10, transport=FakeAccesstrade())
    assert [(p.name, p.price, p.discount) for p in products] == [('Váy maxi hoa', 299000, 199000), ('Áo sơ mi', 159000, None)]
    with pytest.raises(accesstrade.AccesstradeError, match='rejected'):
        accesstrade.list_products(AT_KEY, 'shopee', 10, transport=lambda *a, **k: (401, {}))
    with pytest.raises(accesstrade.AccesstradeError, match='not approved'):
        accesstrade.approved_campaign(AT_KEY, 'shopee', transport=FakeAccesstrade(approved=False))


def test_import_creates_tracked_links_with_price_evidence(client, auth_headers, monkeypatch):
    fake = FakeAccesstrade()
    monkeypatch.setattr(autopilot_routes, 'accesstrade_transport', fake)
    item = campaign(client, auth_headers)
    base = f"/api/v1/campaigns/{item['id']}"
    assert client.get(base + '/accesstrade/products?merchant=shopee', headers=auth_headers).status_code == 409  # not connected
    _connect(client, auth_headers)
    listed = client.get(base + '/accesstrade/products?merchant=shopee', headers=auth_headers)
    assert listed.status_code == 200 and len(listed.json()) == 2 and AT_KEY not in listed.text
    chosen = [{key: value for key, value in product.items() if key in ('product_id', 'name', 'url', 'price', 'discount')} for product in listed.json()]
    request_key = str(uuid4())
    imported = post(client, auth_headers, base + '/accesstrade/import', {'merchant': 'Shopee', 'products': chosen}, key=request_key)
    assert imported.status_code == 201, imported.text
    links = imported.json()['links']
    assert [link['final_url'] for link in links] == ['https://shorten.asia/0abc', 'https://shorten.asia/1abc'] and imported.json()['skipped'] == []
    create = next(call for call in fake.calls if call[1].endswith('/product_link/create'))
    assert create[2]['urls'] == ['https://shopee.vn/vay-1', 'https://shopee.vn/ao-3'] and create[2]['utm_source'] == 'sinhloi'
    # A replay does not call ACCESSTRADE again.
    count = len(fake.calls)
    assert post(client, auth_headers, base + '/accesstrade/import', {'merchant': 'Shopee', 'products': chosen}, key=request_key).json() == imported.json()
    assert len(fake.calls) == count
    db = next(app.dependency_overrides[get_db]())
    product = db.scalar(select(CampaignProduct).where(CampaignProduct.name == 'Váy maxi hoa'))
    source = db.get(CampaignSource, product.price_source_id)
    assert product.price_text == '199.000đ' and source.verification_status == 'VERIFIED' and 'giá gốc 299.000đ' in source.excerpt
    programs = client.get(base + '/programs', headers=auth_headers).json()
    assert programs[0]['name'] == 'ACCESSTRADE · shopee' and programs[0]['link_hosts'] == ['shorten.asia']
    # Importing the same products again skips existing links instead of duplicating them.
    again = post(client, auth_headers, base + '/accesstrade/import', {'merchant': 'shopee', 'products': chosen})
    assert again.json()['links'] == [] and len(again.json()['skipped']) == 2
    assert post(client, auth_headers, base + '/accesstrade/import', {'merchant': 'shopee', 'products': [{**chosen[0], 'url': 'http://shopee.vn/x'}]}).status_code == 422
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == 'campaign.accesstrade_imported')) is not None


def test_import_reports_an_unapproved_merchant(client, auth_headers, monkeypatch):
    monkeypatch.setattr(autopilot_routes, 'accesstrade_transport', FakeAccesstrade(approved=False))
    item = campaign(client, auth_headers)
    _connect(client, auth_headers)
    failed = post(client, auth_headers, f"/api/v1/campaigns/{item['id']}/accesstrade/import",
                  {'merchant': 'shopee', 'products': [{'product_id': 'p1', 'name': 'Váy', 'url': 'https://shopee.vn/vay-1'}]})
    assert failed.status_code == 502 and 'not approved' in failed.json()['detail']


def test_standing_attestations_pass_owner_checks_and_ready_items_are_proposed(client, auth_headers):
    base, link, db = _seed(client, auth_headers)
    campaign_path = base.split('/content/')[0]
    for name in ('MEDIA_RIGHTS', 'LEGAL_ADS_TAX'):
        assert post(client, auth_headers, campaign_path + '/attestations', {'check_name': name, 'note': 'Ảnh của shop, đã khai thuế TNCN'}).status_code == 201
    assert post(client, auth_headers, campaign_path + '/attestations', {'check_name': 'PRICE_CLAIM', 'note': 'xxx'}).status_code == 422
    assert len(client.get(campaign_path + '/attestations', headers=auth_headers).json()) == 2
    # The campaign must be active for proposals.
    current = client.get(campaign_path, headers=auth_headers).json()
    assert post(client, auth_headers, campaign_path + '/status', {'version': current['version'], 'status': 'ACTIVE'}).status_code == 200
    checked = post(client, auth_headers, base + '/checks/run').json()
    results = {c['check_name']: (c['result'], c['method']) for c in checked['checks']}
    assert results['MEDIA_RIGHTS'] == ('PASS', 'OWNER') and results['LEGAL_ADS_TAX'] == ('PASS', 'OWNER') and checked['status'] == 'IN_REVIEW'
    proposals = client.get('/api/v1/proposals', headers=auth_headers).json()
    assert len(proposals) == 1 and proposals[0]['ready'] is True and proposals[0]['open_checks'] == [] and proposals[0]['link_label'] == 'Váy'
    assert post(client, auth_headers, base + '/approve', {'note': 'Đề xuất ổn'}).json()['status'] == 'APPROVED'
    assert client.get('/api/v1/proposals', headers=auth_headers).json() == []
    revoked = post(client, auth_headers, campaign_path + '/attestations/MEDIA_RIGHTS/revoke')
    assert revoked.status_code == 200 and [row['check_name'] for row in revoked.json()['items']] == ['LEGAL_ADS_TAX']
