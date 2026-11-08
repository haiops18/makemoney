"""Step 7A Level B review: Owner edits, checks, approve/reject, export and publish records.

Lifecycle: DRAFT → (checks) → CHECK_FAILED | IN_REVIEW → APPROVED | REJECTED;
APPROVED → READY_TO_PUBLISH on export → PUBLISHED when the Owner records a post.
Any Owner edit creates a new immutable version and returns the item to DRAFT. The app
never publishes: export only returns text, and a publish record is the Owner's own report.
"""
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_brain.content_contract import BODY_LIMITS
from app.campaigns.review import PostUnavailable, compose_post, ensure_checks
from app.api.campaign_routes import IdempotencyKey, _audit, _campaign, _save
from app.api.content_routes import ContentDetail, _content_response
from app.api.opportunity_routes import _idempotent
from app.auth.dependencies import require_owner
from app.campaigns.links import LinkRuleError, safe_url
from app.db.models import ContentCheck, ContentItem, ContentPublishRecord, ContentVersion
from app.db.session import get_db

router = APIRouter(prefix='/api/v1/campaigns', dependencies=[Depends(require_owner)], tags=['campaign-review'])
EDITABLE = {'DRAFT', 'CHECK_FAILED', 'IN_REVIEW', 'APPROVED', 'READY_TO_PUBLISH', 'REJECTED'}


class Note(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    note: str = Field(min_length=1, max_length=1000)


class VersionCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    base_version_no: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)
    hashtags: list[str] = Field(default_factory=list, max_length=15)
    cta: str = Field(min_length=1, max_length=300)

    @field_validator('hashtags')
    @classmethod
    def single_words(cls, value: list[str]) -> list[str]:
        cleaned = [tag.strip().lstrip('#') for tag in value if tag.strip()]
        if any(len(tag) > 50 or any(char.isspace() for char in tag) for tag in cleaned):
            raise ValueError('Hashtags must be single words of at most 50 characters')
        return cleaned


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    format: Literal['text', 'markdown'] = 'text'


class ExportResponse(BaseModel):
    content_id: UUID
    version_no: int
    format: str
    text: str
    link_url: str
    disclosure_added: bool
    status: str


class PublishCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    channel: str = Field(min_length=1, max_length=100)
    published_url: str = Field(min_length=1, max_length=2048)
    published_at: datetime

    @field_validator('published_url')
    @classmethod
    def web_url(cls, value: str) -> str:
        try:
            return safe_url(value)
        except LinkRuleError as exc:
            raise ValueError(str(exc)) from None

    @field_validator('published_at')
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError('published_at needs a timezone')
        return value


def _item(db: Session, campaign_id: UUID, content_id: UUID) -> ContentItem:
    _campaign(db, campaign_id, lock=True, editable=True)
    item = db.scalar(select(ContentItem).where(ContentItem.id == content_id, ContentItem.campaign_id == campaign_id).with_for_update())
    if item is None:
        raise HTTPException(status_code=404, detail='Content not found')
    return item


def _version(db: Session, item: ContentItem) -> ContentVersion:
    return db.scalar(select(ContentVersion).where(ContentVersion.content_id == item.id, ContentVersion.version_no == item.current_version_no))


def _require(item: ContentItem, *allowed: str) -> None:
    if item.status not in allowed:
        raise HTTPException(status_code=409, detail=f'Not allowed while the content is {item.status}')


def _decide(item: ContentItem, status: str, actor: str | None = None, note: str | None = None) -> None:
    item.status, item.decided_by, item.decided_at, item.decision_note = status, actor, datetime.now(UTC) if actor else None, note


def _detail(db: Session, item: ContentItem) -> ContentDetail:
    db.flush()
    return _content_response(db, item, detail=True)


@router.post('/{campaign_id}/content/{content_id}/versions', response_model=ContentDetail, status_code=201)
def edit_content(campaign_id: UUID, content_id: UUID, body: VersionCreate, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Owner edit: a new immutable version based on the current one; the item returns to DRAFT."""
    path, payload = f'/api/v1/campaigns/{campaign_id}/content/{content_id}/versions', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, ContentDetail):
        return existing
    item = _item(db, campaign_id, content_id)
    _require(item, *EDITABLE)
    if body.base_version_no != item.current_version_no:
        raise HTTPException(status_code=409, detail='The content changed; reload and edit the latest version')
    if len(body.body) > BODY_LIMITS[item.content_type]:
        raise HTTPException(status_code=422, detail=f'The body exceeds {BODY_LIMITS[item.content_type]} characters for this content type')
    base = _version(db, item)
    version = ContentVersion(content_id=item.id, version_no=base.version_no + 1, base_version_no=base.version_no, title=body.title, body=body.body, hashtags=body.hashtags,
                             cta=body.cta, claims=base.claims, author_kind='OWNER', invocation_id=None, author=actor)
    db.add(version)
    item.current_version_no = version.version_no
    _decide(item, 'DRAFT')
    _audit(db, actor, 'content.edited', 'content_item', item.id, version_no=version.version_no, base_version_no=base.version_no)
    return _save(db, actor, key, 'POST', path, payload, _detail(db, item), 201, response, ContentDetail)


@router.post('/{campaign_id}/content/{content_id}/checks/run', response_model=ContentDetail)
def check_content(campaign_id: UUID, content_id: UUID, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Run the rule checks once per version. A FAIL sends the item to CHECK_FAILED, otherwise to IN_REVIEW."""
    path, payload = f'/api/v1/campaigns/{campaign_id}/content/{content_id}/checks/run', {}
    if existing := _idempotent(db, actor, key, 'POST', path, payload, ContentDetail):
        return existing
    item = _item(db, campaign_id, content_id)
    _require(item, 'DRAFT', 'CHECK_FAILED', 'IN_REVIEW')
    ensure_checks(db, item)
    _audit(db, actor, 'content.checked', 'content_item', item.id, version_no=item.current_version_no, status=item.status)
    return _save(db, actor, key, 'POST', path, payload, _detail(db, item), 200, response, ContentDetail)


@router.post('/{campaign_id}/content/{content_id}/checks/{check_name}/attest', response_model=ContentDetail)
def attest_check(campaign_id: UUID, content_id: UUID, check_name: str, body: Note, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """The Owner's own confirmation of a NEEDS_OWNER check. A FAIL can only be fixed by editing."""
    path, payload = f'/api/v1/campaigns/{campaign_id}/content/{content_id}/checks/{check_name}/attest', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, ContentDetail):
        return existing
    item = _item(db, campaign_id, content_id)
    _require(item, 'IN_REVIEW')
    check = db.scalar(select(ContentCheck).where(ContentCheck.version_id == _version(db, item).id, ContentCheck.check_name == check_name).with_for_update())
    if check is None:
        raise HTTPException(status_code=404, detail='Check not found')
    if check.result != 'NEEDS_OWNER':
        raise HTTPException(status_code=409, detail='Only a check that needs the Owner can be confirmed')
    check.result, check.method, check.attested_by, check.attested_at = 'PASS', 'OWNER', actor, datetime.now(UTC)
    check.note = f'{check.note} Owner: {body.note}'[:1000]
    _audit(db, actor, 'content.check_attested', 'content_item', item.id, check=check_name, version_no=item.current_version_no)
    return _save(db, actor, key, 'POST', path, payload, _detail(db, item), 200, response, ContentDetail)


@router.post('/{campaign_id}/content/{content_id}/approve', response_model=ContentDetail)
def approve_content(campaign_id: UUID, content_id: UUID, body: Note, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path, payload = f'/api/v1/campaigns/{campaign_id}/content/{content_id}/approve', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, ContentDetail):
        return existing
    item = _item(db, campaign_id, content_id)
    _require(item, 'IN_REVIEW')
    open_checks = list(db.scalars(select(ContentCheck.check_name).where(ContentCheck.version_id == _version(db, item).id, ContentCheck.result != 'PASS')))
    if open_checks:
        raise HTTPException(status_code=409, detail=f'Resolve these checks first: {", ".join(sorted(open_checks))}')
    _decide(item, 'APPROVED', actor, body.note)
    _audit(db, actor, 'content.approved', 'content_item', item.id, version_no=item.current_version_no)
    return _save(db, actor, key, 'POST', path, payload, _detail(db, item), 200, response, ContentDetail)


@router.post('/{campaign_id}/content/{content_id}/reject', response_model=ContentDetail)
def reject_content(campaign_id: UUID, content_id: UUID, body: Note, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path, payload = f'/api/v1/campaigns/{campaign_id}/content/{content_id}/reject', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, ContentDetail):
        return existing
    item = _item(db, campaign_id, content_id)
    _require(item, 'DRAFT', 'CHECK_FAILED', 'IN_REVIEW', 'APPROVED', 'READY_TO_PUBLISH')
    _decide(item, 'REJECTED', actor, body.note)
    _audit(db, actor, 'content.rejected', 'content_item', item.id, version_no=item.current_version_no)
    return _save(db, actor, key, 'POST', path, payload, _detail(db, item), 200, response, ContentDetail)


@router.post('/{campaign_id}/content/{content_id}/export', response_model=ExportResponse)
def export_content(campaign_id: UUID, content_id: UUID, body: ExportRequest, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Return the approved text with the real link and the campaign disclosure, for the Owner to post."""
    path, payload = f'/api/v1/campaigns/{campaign_id}/content/{content_id}/export', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, ExportResponse):
        return existing
    item = _item(db, campaign_id, content_id)
    _require(item, 'APPROVED', 'READY_TO_PUBLISH', 'PUBLISHED')
    try:
        text, link_url, add_disclosure, version_no = compose_post(db, item, body.format)
    except PostUnavailable as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    if item.status == 'APPROVED':
        item.status = 'READY_TO_PUBLISH'
    _audit(db, actor, 'content.exported', 'content_item', item.id, version_no=version_no, format=body.format, disclosure_added=add_disclosure)
    db.flush()
    result = ExportResponse(content_id=item.id, version_no=version_no, format=body.format, text=text, link_url=link_url,
                            disclosure_added=add_disclosure, status=item.status)
    return _save(db, actor, key, 'POST', path, payload, result, 200, response, ExportResponse)


@router.post('/{campaign_id}/content/{content_id}/publish-records', response_model=ContentDetail, status_code=201)
def record_publish(campaign_id: UUID, content_id: UUID, body: PublishCreate, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Record where the Owner posted an exported item. The app itself never posts."""
    path, payload = f'/api/v1/campaigns/{campaign_id}/content/{content_id}/publish-records', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, ContentDetail):
        return existing
    item = _item(db, campaign_id, content_id)
    _require(item, 'READY_TO_PUBLISH', 'PUBLISHED')
    if body.published_at > datetime.now(UTC) + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail='published_at cannot be in the future')
    if db.scalar(select(ContentPublishRecord.id).where(ContentPublishRecord.content_id == item.id, ContentPublishRecord.published_url == body.published_url)):
        raise HTTPException(status_code=409, detail='This post was already recorded')
    db.add(ContentPublishRecord(content_id=item.id, version_no=item.current_version_no, channel=body.channel, published_url=body.published_url,
                                published_at=body.published_at, recorded_by=actor))
    item.status = 'PUBLISHED'
    _audit(db, actor, 'content.publish_recorded', 'content_item', item.id, version_no=item.current_version_no, channel=body.channel)
    return _save(db, actor, key, 'POST', path, payload, _detail(db, item), 201, response, ContentDetail)
