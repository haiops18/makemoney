"""Step 7A Level B review: rule checks and the Owner review lifecycle (no AI, no publishing)."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.campaigns.checks import Context, Draft, run_checks, similarity
from app.db.models import AIResearchRun, AIResearchSource, AuditEvent, ContentItem, ContentVersion
from app.db.session import get_db
from app.main import app
from test_campaigns import campaign, post, program

VERIFIED = str(uuid4())


def checks(**draft):
    base = {'title': 'Váy hè', 'body': 'Hoa hồng 3.68%, giá 199.000đ. Xem tại {{AFFILIATE_LINK}}', 'cta': 'Mua ngay', 'hashtags': ['vay'],
            'claims': [{'classification': 'FACT', 'statement': 'Hoa hồng 3.68%', 'source_ids': [VERIFIED]}], 'author_kind': 'AI'}
    context = Context(disclosure_text=draft.pop('disclosure', 'Có link tiếp thị liên kết.'), verified_source_ids={VERIFIED},
                      verified_texts=['Thời trang nữ 3.68%', '199.000đ'], other_bodies=draft.pop('others', []))
    return {result.check: result for result in run_checks(Draft(**{**base, **draft}), context)}


def test_clean_ai_draft_passes_rules_but_human_checks_wait_for_the_owner():
    result = checks()
    assert {name for name, item in result.items() if item.result == 'PASS'} == {'LINK_PLACEHOLDER', 'DISCLOSURE', 'CLAIM_EVIDENCE', 'PRICE_CLAIM', 'PLATFORM_POLICY', 'EXTRA_LINKS', 'DUPLICATE'}
    assert result['MEDIA_RIGHTS'].result == result['LEGAL_ADS_TAX'].result == 'NEEDS_OWNER'


def test_rule_failures():
    assert checks(body='Không có link')['LINK_PLACEHOLDER'].result == 'FAIL'
    assert checks(disclosure=None)['DISCLOSURE'].result == 'NEEDS_OWNER'
    assert checks(claims=[{'classification': 'FACT', 'statement': 'x', 'source_ids': [str(uuid4())]}])['CLAIM_EVIDENCE'].result == 'FAIL'
    assert checks(author_kind='OWNER')['CLAIM_EVIDENCE'].result == 'NEEDS_OWNER'
    priced = checks(body='Chỉ 149.000đ, giảm 50%! {{AFFILIATE_LINK}}')['PRICE_CLAIM']
    assert priced.result == 'FAIL' and priced.evidence == ['149.000đ', '50%']
    policy = checks(body='Cam kết chất lượng tốt nhất {{AFFILIATE_LINK}}')['PLATFORM_POLICY']
    assert policy.result == 'FAIL' and policy.evidence == ['cam kết', 'tốt nhất']
    assert checks(cta='Xem thêm ở example.com')['EXTRA_LINKS'].result == 'NEEDS_OWNER'
    body = 'Váy maxi mùa hè chất liệu cotton thoáng mát mặc đi làm đi chơi đều đẹp {{AFFILIATE_LINK}}'
    assert checks(body=body, others=[body])['DUPLICATE'].result == 'FAIL'
    assert similarity('a b c d', 'w x y z') == 0


def _seed(client, headers, *, disclosure=True):
    item = campaign(client, headers)
    path = f"/api/v1/campaigns/{item['id']}"
    if disclosure:
        client.patch(path, json={'version': 1, 'disclosure_text': 'Có link tiếp thị liên kết.'}, headers={**headers, 'Idempotency-Key': str(uuid4())})
    plan = program(client, headers, item['id'])
    link = post(client, headers, path + '/links', {'program_id': plan['id'], 'label': 'Váy', 'original_url': 'https://s.shopee.vn/AbC', 'tracking_params': {'sub_id': 'r1'}}).json()
    db = next(app.dependency_overrides[get_db]())
    run = AIResearchRun(kind='CONTENT', campaign_id=UUID(item['id']), objective='batch', max_cost_usd='1', status='DRAFT', created_by='owner',
                        content_spec_json={'request': {'terms': [], 'product': None}, 'affiliate_link_id': link['id']})
    db.add(run)
    db.flush()
    source = AIResearchSource(research_run_id=run.id, source_name='GHN', excerpt='Thời trang nữ 3.68%', verification_status='VERIFIED', verified_by='owner', verified_at=datetime.now(UTC))
    db.add(source)
    db.flush()
    content = ContentItem(campaign_id=UUID(item['id']), batch_run_id=run.id, source_invocation_id=uuid4(), item_index=0, affiliate_link_id=UUID(link['id']), content_type='SOCIAL_POST',
                          language='vi', status='DRAFT', current_version_no=1)
    db.add(content)
    db.flush()
    db.add(ContentVersion(content_id=content.id, version_no=1, title='Váy hè', body='Hoa hồng 3.68%. Xem tại {{AFFILIATE_LINK}}', hashtags=['vay'], cta='Mua ngay',
                          claims=[{'classification': 'FACT', 'statement': 'Hoa hồng 3.68%', 'source_ids': [str(source.id)]}], author_kind='AI', invocation_id=uuid4(), author='content-agent'))
    db.commit()
    return f"{path}/content/{content.id}", link, db


def test_owner_review_lifecycle_to_publish_record(client, auth_headers):
    base, link, db = _seed(client, auth_headers)
    assert post(client, auth_headers, base + '/approve', {'note': 'ok'}).status_code == 409  # not reviewed yet
    checked = post(client, auth_headers, base + '/checks/run')
    assert checked.status_code == 200, checked.text
    detail = checked.json()
    assert detail['status'] == 'IN_REVIEW'
    assert {c['check_name'] for c in detail['checks'] if c['result'] == 'NEEDS_OWNER'} == {'MEDIA_RIGHTS', 'LEGAL_ADS_TAX'}
    assert post(client, auth_headers, base + '/approve', {'note': 'ok'}).json()['detail'] == 'Resolve these checks first: LEGAL_ADS_TAX, MEDIA_RIGHTS'
    assert post(client, auth_headers, base + '/checks/PRICE_CLAIM/attest', {'note': 'x'}).status_code == 409
    for name in ('MEDIA_RIGHTS', 'LEGAL_ADS_TAX'):
        assert post(client, auth_headers, f'{base}/checks/{name}/attest', {'note': 'Ảnh tự chụp; đã khai thuế'}).status_code == 200
    assert post(client, auth_headers, base + '/export', {'format': 'text'}).status_code == 409  # not approved
    approved = post(client, auth_headers, base + '/approve', {'note': 'Nội dung ổn'})
    assert approved.status_code == 200 and approved.json()['status'] == 'APPROVED' and approved.json()['decided_by'] == 'owner'
    exported = post(client, auth_headers, base + '/export', {'format': 'text'})
    assert exported.status_code == 200, exported.text
    text = exported.json()['text']
    assert 'https://s.shopee.vn/AbC?sub_id=r1' in text and '{{AFFILIATE_LINK}}' not in text and text.endswith('Có link tiếp thị liên kết.')
    assert exported.json()['status'] == 'READY_TO_PUBLISH' and exported.json()['disclosure_added'] is True
    record = {'channel': 'Facebook Page', 'published_url': 'https://facebook.com/p/1', 'published_at': datetime.now(UTC).isoformat()}
    assert post(client, auth_headers, base + '/publish-records', {**record, 'published_url': 'javascript:alert(1)'}).status_code == 422
    assert post(client, auth_headers, base + '/publish-records', {**record, 'published_at': '2099-01-01T00:00:00Z'}).status_code == 422
    published = post(client, auth_headers, base + '/publish-records', record)
    assert published.status_code == 201 and published.json()['status'] == 'PUBLISHED' and len(published.json()['publish_records']) == 1
    assert post(client, auth_headers, base + '/publish-records', record).status_code == 409
    assert post(client, auth_headers, base + '/versions', {'base_version_no': 1, 'title': 'x', 'body': 'y {{AFFILIATE_LINK}}', 'cta': 'z'}).status_code == 409
    actions = set(db.scalars(select(AuditEvent.action).where(AuditEvent.action.like('content.%'))))
    assert {'content.checked', 'content.check_attested', 'content.approved', 'content.exported', 'content.publish_recorded'} <= actions


def test_owner_edit_creates_a_version_and_requires_new_checks(client, auth_headers):
    base, link, db = _seed(client, auth_headers, disclosure=False)
    detail = post(client, auth_headers, base + '/checks/run').json()
    assert {c['check_name']: c['result'] for c in detail['checks']}['DISCLOSURE'] == 'NEEDS_OWNER'
    stale = post(client, auth_headers, base + '/versions', {'base_version_no': 2, 'title': 'x', 'body': 'y {{AFFILIATE_LINK}}', 'cta': 'z'})
    assert stale.status_code == 409
    edited = post(client, auth_headers, base + '/versions', {'base_version_no': 1, 'title': 'Váy hè mới', 'body': 'Cam kết đẹp nhất! {{AFFILIATE_LINK}}', 'cta': 'Mua', 'hashtags': ['#vay']})
    assert edited.status_code == 201, edited.text
    data = edited.json()
    assert data['status'] == 'DRAFT' and data['current_version']['version_no'] == 2 and data['current_version']['author_kind'] == 'OWNER'
    assert [v['version_no'] for v in data['versions']] == [1, 2] and data['versions'][0]['body'].startswith('Hoa hồng') and data['checks'] == []
    assert data['current_version']['hashtags'] == ['vay']
    failed = post(client, auth_headers, base + '/checks/run').json()
    assert failed['status'] == 'CHECK_FAILED'
    results = {c['check_name']: c['result'] for c in failed['checks']}
    assert results['PLATFORM_POLICY'] == 'FAIL' and results['CLAIM_EVIDENCE'] == 'NEEDS_OWNER'
    assert post(client, auth_headers, base + '/checks/MEDIA_RIGHTS/attest', {'note': 'x'}).status_code == 409  # only in review
    rejected = post(client, auth_headers, base + '/reject', {'note': 'Không phù hợp'})
    assert rejected.json()['status'] == 'REJECTED' and rejected.json()['decision_note'] == 'Không phù hợp'
    assert db.scalar(select(func.count()).select_from(ContentVersion).where(ContentVersion.content_id == UUID(data['id']))) == 2


def test_export_refuses_a_retired_link(client, auth_headers):
    base, link, db = _seed(client, auth_headers)
    post(client, auth_headers, base + '/checks/run')
    for name in ('MEDIA_RIGHTS', 'LEGAL_ADS_TAX'):
        post(client, auth_headers, f'{base}/checks/{name}/attest', {'note': 'ok'})
    assert post(client, auth_headers, base + '/approve', {'note': 'ok'}).status_code == 200
    campaign_path = base.split('/content/')[0]
    assert post(client, auth_headers, f"{campaign_path}/links/{link['id']}/retire").status_code == 200
    assert post(client, auth_headers, base + '/export', {'format': 'markdown'}).status_code == 409
