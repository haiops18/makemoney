"""Scheduled posting of Owner-approved content to a Facebook Page (Step 7B, Level C after approval).

Rules (fail closed):
- Only items the Owner APPROVED, in an ACTIVE campaign whose schedule the Owner turned on,
  with a Facebook integration whose last connection check was OK.
- The exact approved version is posted; an edit, rejection, retired link or pause cancels it.
- One attempt per post, never retried. Any failure or unknown outcome pauses the schedule.
"""
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import select

from app.ai_brain.credentials import CredentialUnavailable, decrypt_credential
from app.ai_brain.network import provider_request
from app.campaigns.review import PostUnavailable, compose_post
from app.db.models import AuditEvent, Campaign, ContentItem, ContentPublishRecord, Integration, PostingSchedule, ScheduledPost
from app.integrations.kinds import KINDS

VN = timezone(timedelta(hours=7))
LEAD = timedelta(minutes=2)
STUCK = timedelta(minutes=10)
QUEUE_DAYS = 14


def _audit(db, action: str, entity_type: str, entity_id, **detail) -> None:
    db.add(AuditEvent(actor='posting-worker', action=action, entity_type=entity_type, entity_id=entity_id, detail={k: str(v) for k, v in detail.items()}))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def next_slots(hours: list[int], taken: set[datetime], now: datetime, count: int) -> list[datetime]:
    """Free slots at the given Vietnam hours, starting after now + LEAD, at most QUEUE_DAYS ahead."""
    slots, day = [], now.astimezone(VN).date()
    for offset in range(QUEUE_DAYS):
        for hour in sorted(set(hours)):
            slot = datetime(day.year, day.month, day.day, hour, tzinfo=VN).astimezone(UTC) + timedelta(days=offset)
            if slot > now + LEAD and slot not in taken:
                slots.append(slot)
                if len(slots) == count:
                    return slots
    return slots


def pause(db, schedule: PostingSchedule, reason: str) -> None:
    schedule.enabled, schedule.paused_reason = False, reason[:300]
    _audit(db, 'posting.paused', 'posting_schedule', schedule.id, campaign_id=schedule.campaign_id, reason=reason[:300])


def queue_approved(db, now: datetime) -> int:
    """Give every APPROVED item of an enabled schedule a free slot."""
    queued = 0
    schedules = db.scalars(select(PostingSchedule).join(Campaign, Campaign.id == PostingSchedule.campaign_id)
                           .where(PostingSchedule.enabled.is_(True), Campaign.status == 'ACTIVE').with_for_update(of=PostingSchedule, skip_locked=True))
    for schedule in schedules:
        active = select(ScheduledPost.content_id).where(ScheduledPost.status.in_(('QUEUED', 'POSTING', 'POSTED')))
        items = list(db.scalars(select(ContentItem).where(ContentItem.campaign_id == schedule.campaign_id, ContentItem.status == 'APPROVED', ContentItem.id.not_in(active))
                                .order_by(ContentItem.decided_at, ContentItem.id).limit(50)))
        if not items:
            continue
        taken = {_aware(slot) for slot in db.scalars(select(ScheduledPost.slot_at).where(ScheduledPost.integration_id == schedule.integration_id, ScheduledPost.status.in_(('QUEUED', 'POSTING'))))}
        for item, slot in zip(items, next_slots(schedule.hours, taken, now, len(items))):
            post = ScheduledPost(campaign_id=schedule.campaign_id, content_id=item.id, version_no=item.current_version_no, integration_id=schedule.integration_id, slot_at=slot, status='QUEUED')
            db.add(post)
            db.flush()
            _audit(db, 'posting.queued', 'scheduled_post', post.id, content_id=item.id, slot_at=slot.isoformat())
            queued += 1
    return queued


def _recover(db, now: datetime) -> bool:
    stuck = db.scalar(select(ScheduledPost).where(ScheduledPost.status == 'POSTING', ScheduledPost.attempted_at < now - STUCK).with_for_update(skip_locked=True).limit(1))
    if stuck is None:
        return False
    stuck.status, stuck.error = 'FAILED', 'Outcome unknown after a crash; check the Page before posting again'
    schedule = db.scalar(select(PostingSchedule).where(PostingSchedule.campaign_id == stuck.campaign_id).with_for_update())
    if schedule is not None:
        pause(db, schedule, stuck.error)
    _audit(db, 'posting.failed', 'scheduled_post', stuck.id, reason=stuck.error)
    return True


def _claim(db, now: datetime):
    post = db.scalar(select(ScheduledPost).where(ScheduledPost.status == 'QUEUED', ScheduledPost.slot_at <= now).order_by(ScheduledPost.slot_at, ScheduledPost.id)
                     .with_for_update(skip_locked=True).limit(1))
    if post is None:
        return None
    schedule = db.scalar(select(PostingSchedule).where(PostingSchedule.campaign_id == post.campaign_id).with_for_update())
    campaign = db.get(Campaign, post.campaign_id)
    item = db.scalar(select(ContentItem).where(ContentItem.id == post.content_id).with_for_update())
    integration = db.get(Integration, post.integration_id)

    def cancel(reason: str):
        post.status, post.error = 'CANCELLED', reason
        _audit(db, 'posting.cancelled', 'scheduled_post', post.id, reason=reason)
        return False
    if schedule is None or not schedule.enabled or schedule.integration_id != post.integration_id or campaign.status != 'ACTIVE':
        return cancel('The schedule is off or the campaign is not active')
    if item.status != 'APPROVED' or item.current_version_no != post.version_no:
        return cancel('The content changed after approval')
    if integration is None or integration.archived or not integration.enabled or integration.kind != 'FACEBOOK_PAGE' or not integration.encrypted_secret:
        pause(db, schedule, 'The Facebook Page integration is unavailable')
        return cancel('The Facebook Page integration is unavailable')
    try:
        text, link_url, _, version_no = compose_post(db, item)
        token = decrypt_credential(integration.id, integration.encrypted_secret)
    except PostUnavailable as error:
        return cancel(str(error))
    except CredentialUnavailable:
        pause(db, schedule, 'The Page token cannot be decrypted; replace it on the Integrations page')
        return cancel('The Page token cannot be decrypted')
    post.status, post.attempted_at = 'POSTING', now
    _audit(db, 'posting.started', 'scheduled_post', post.id, content_id=item.id, version_no=version_no)
    config = dict(integration.config_json)
    return post.id, text, link_url, token, config


def posting_tick(factory, *, transport=provider_request, now: datetime | None = None) -> bool:
    """Recover, queue and post at most one due item. Returns True when something changed."""
    now = now or datetime.now(UTC)
    with factory.begin() as db:
        recovered = _recover(db, now)
    with factory.begin() as db:
        queued = queue_approved(db, now)
    with factory.begin() as db:
        claimed = _claim(db, now)
    if not claimed:
        return recovered or bool(queued) or claimed is False
    post_id, text, link_url, token, config = claimed
    host = KINDS['FACEBOOK_PAGE'].host
    try:
        code, raw = transport('POST', f"https://{host}/{config['graph_version']}/{config['page_id']}/feed", {host}, {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                              {'message': text, 'link': link_url}, 30)
        external = raw.get('id') if isinstance(raw, dict) and 200 <= code < 300 else None
        error = None if isinstance(external, str) and 0 < len(external) <= 100 else (
            'Facebook rejected the Page token' if code in (401, 403) else 'Facebook is rate limiting' if code == 429 else f'Facebook returned an error ({code})')
    except Exception:
        external, error = None, 'Facebook could not be reached; the post may or may not exist, check the Page'
    finally:
        token = None
    with factory.begin() as db:
        post = db.scalar(select(ScheduledPost).where(ScheduledPost.id == post_id).with_for_update())
        schedule = db.scalar(select(PostingSchedule).where(PostingSchedule.campaign_id == post.campaign_id).with_for_update())
        if error:
            post.status, post.error = 'FAILED', error
            _audit(db, 'posting.failed', 'scheduled_post', post.id, reason=error)
            if schedule is not None:
                pause(db, schedule, error)
            return True
        post.status, post.external_post_id = 'POSTED', external
        item = db.scalar(select(ContentItem).where(ContentItem.id == post.content_id).with_for_update())
        db.add(ContentPublishRecord(content_id=item.id, version_no=post.version_no, channel='Facebook Page', published_url=f'https://www.facebook.com/{external}',
                                    published_at=now, recorded_by='posting-worker'))
        item.status = 'PUBLISHED'
        _audit(db, 'posting.posted', 'scheduled_post', post.id, content_id=item.id, external_post_id=external)
    return True
