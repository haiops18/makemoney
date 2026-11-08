"""Step 7B scheduled posting on PostgreSQL: approved items post to a fake Facebook Graph API at their slot.

No request leaves the process. A failure pauses the schedule; nothing is retried.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select

import app.api.integration_routes as integration_routes
from app.campaigns.posting import VN, next_slots, posting_tick
from app.db.models import ContentItem, ContentPublishRecord, ScheduledPost
from test_postgres_ai_pipeline import HEADERS, key, pg  # noqa: F401
from test_postgres_content_batches import FakeContentProvider, SECRET_LINK, _activate, _batch, _campaign, _content_profile, _run_batch

PAGE = '1234567890'


class FakeGraph:
    def __init__(self, code=200):
        self.code, self.calls = code, []

    def __call__(self, method, url, hosts, headers, payload, timeout, query=None):
        self.calls.append((method, url, hosts, headers, payload))
        return self.code, ({'id': f'{PAGE}_{len(self.calls)}'} if self.code == 200 else {'error': {'message': 'nope'}})


def test_next_slots_use_vietnam_hours_and_skip_taken():
    now = datetime(2026, 11, 8, 2, 0, tzinfo=UTC)  # 09:00 in Vietnam
    first, second, third = next_slots([8, 20], set(), now, 3)
    assert [slot.astimezone(VN).strftime('%d %H') for slot in (first, second, third)] == ['08 20', '09 08', '09 20']
    assert next_slots([8, 20], {first}, now, 1) == [second]


@pytest.mark.postgres
def test_approved_items_post_on_schedule_and_a_failure_pauses(pg, monkeypatch):
    client, factory = pg
    _content_profile(client)
    from test_postgres_ai_pipeline import _enable_consent, _policies
    internal, ai = _policies(client)
    _enable_consent(client, ai)
    _, base, link_id = _campaign(client)
    current = client.get(base, headers=HEADERS).json()
    assert client.patch(base, json={'version': current['version'], 'disclosure_text': 'Có link tiếp thị liên kết.'}, headers=key()).status_code == 200
    _activate(client, base)
    for name in ('MEDIA_RIGHTS', 'LEGAL_ADS_TAX'):
        assert client.post(base + '/attestations', json={'check_name': name, 'note': 'Owner confirmed for the campaign'}, headers=key()).status_code == 201
    batch = _batch(client, base, link_id, content_types=['SOCIAL_POST', 'SHORT_CAPTION'], count_per_type=1).json()
    _run_batch(client, factory, batch, FakeContentProvider())
    items = client.get(base + '/content', headers=HEADERS).json()
    assert {item['status'] for item in items} == {'IN_REVIEW'}  # checks ran automatically
    ready = [proposal for proposal in client.get('/api/v1/proposals', headers=HEADERS).json() if proposal['campaign_id'] == base.rsplit('/', 1)[1]]
    assert len(ready) == 2 and all(proposal['ready'] for proposal in ready)

    monkeypatch.setattr(integration_routes, 'connection_transport', lambda *a, **k: (200, {'id': PAGE, 'name': 'Váy hè'}))
    page = client.post('/api/v1/integrations', json={'kind': 'FACEBOOK_PAGE', 'label': f'Page {key()["Idempotency-Key"][:6]}', 'config': {'page_id': PAGE}, 'secret': 'EAAG-page'}, headers=key()).json()
    schedule = {'integration_id': page['id'], 'enabled': True, 'hours': [8, 20]}
    assert client.put(base + '/schedule', json=schedule, headers=key()).status_code == 409  # Page not checked yet
    assert client.post(f"/api/v1/integrations/{page['id']}/test", headers=key()).json()['last_check_status'] == 'OK'
    assert client.put(base + '/schedule', json=schedule, headers=key()).json()['enabled'] is True

    for proposal in ready:
        assert client.post(f"{base}/content/{proposal['content_id']}/approve", json={'note': 'Đăng được'}, headers=key()).status_code == 200
    graph = FakeGraph()
    now = datetime.now(UTC)
    assert posting_tick(factory, transport=graph, now=now) is True  # queues both
    posts = client.get(base + '/scheduled-posts', headers=HEADERS).json()
    assert [post['status'] for post in posts] == ['QUEUED', 'QUEUED'] and graph.calls == []
    first_slot = min(datetime.fromisoformat(post['slot_at']) for post in posts)
    assert posting_tick(factory, transport=graph, now=first_slot + timedelta(minutes=1)) is True
    assert len(graph.calls) == 1
    method, url, hosts, headers, payload = graph.calls[0]
    assert (method, url, hosts) == ('POST', f'https://graph.facebook.com/v26.0/{PAGE}/feed', {'graph.facebook.com'})
    assert headers['Authorization'] == 'Bearer EAAG-page' and payload['link'] == SECRET_LINK
    assert SECRET_LINK in payload['message'] and '{{AFFILIATE_LINK}}' not in payload['message'] and payload['message'].endswith('Có link tiếp thị liên kết.')
    with factory() as db:
        posted = db.scalar(select(ScheduledPost).where(ScheduledPost.status == 'POSTED', ScheduledPost.campaign_id == UUID(base.rsplit('/', 1)[1])))
        item = db.get(ContentItem, posted.content_id)
        record = db.scalar(select(ContentPublishRecord).where(ContentPublishRecord.content_id == item.id))
        assert item.status == 'PUBLISHED' and record.published_url == f'https://www.facebook.com/{PAGE}_1' and record.recorded_by == 'posting-worker'
    # Nothing is due before the next slot, and a post is never retried.
    assert posting_tick(factory, transport=graph, now=first_slot + timedelta(minutes=2)) is False and len(graph.calls) == 1

    failing = FakeGraph(code=500)
    second_slot = max(datetime.fromisoformat(post['slot_at']) for post in posts)
    assert posting_tick(factory, transport=failing, now=second_slot + timedelta(minutes=1)) is True
    state = client.get(base + '/schedule', headers=HEADERS).json()
    assert state['enabled'] is False and 'error (500)' in state['paused_reason']
    statuses = sorted(post['status'] for post in client.get(base + '/scheduled-posts', headers=HEADERS).json())
    assert statuses == ['FAILED', 'POSTED']
    assert posting_tick(factory, transport=failing, now=second_slot + timedelta(days=1)) is False and len(failing.calls) == 1
    # A failed (maybe-posted) item leaves automatic posting, so turning the schedule back on cannot post it twice.
    with factory() as db:
        failed = db.scalar(select(ScheduledPost).where(ScheduledPost.status == 'FAILED', ScheduledPost.campaign_id == UUID(base.rsplit('/', 1)[1])))
        assert db.get(ContentItem, failed.content_id).status == 'READY_TO_PUBLISH'
    assert client.put(base + '/schedule', json=schedule, headers=key()).json()['enabled'] is True
    assert posting_tick(factory, transport=failing, now=second_slot + timedelta(days=2)) is False and len(failing.calls) == 1
    # Replacing the Page token pauses the schedule until the new account is checked.
    assert client.patch(f"/api/v1/integrations/{page['id']}", json={'secret': 'EAAG-new'}, headers=key()).status_code == 200
    paused = client.get(base + '/schedule', headers=HEADERS).json()
    assert paused['enabled'] is False and 'changed' in paused['paused_reason']
    assert client.put(base + '/schedule', json=schedule, headers=key()).status_code == 409
