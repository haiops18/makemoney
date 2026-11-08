"""Step 7B production helpers: ACCESSTRADE products and links, standing attestations, proposals.

- Listing ACCESSTRADE products is a free read. Importing creates tracking links through the
  official API on the Owner's click, then stores product, price evidence and link.
- A standing attestation is the Owner's own confirmation, per campaign, of a check that always
  needs the Owner (media rights, ads/e-commerce/tax). It applies to checks run after it.
- Proposals are items that passed every check and wait for the Owner's approval.
"""
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.campaign_routes import IdempotencyKey, _audit, _campaign, _save
from app.api.campaign_schemas import LinkResponse
from app.api.integration_routes import active_secret
from app.api.opportunity_routes import _idempotent
from app.auth.dependencies import require_owner
from app.campaigns.links import HOST as HOST_NAME, LinkRuleError, safe_url
from app.campaigns.review import open_checks
from app.db.models import (AffiliateLink, AffiliateProgram, Campaign, CampaignAttestation, CampaignProduct, CampaignSource, ContentItem, ContentVersion)
from app.db.session import get_db
from app.integrations import accesstrade

router = APIRouter(prefix='/api/v1', dependencies=[Depends(require_owner)], tags=['autopilot'])
# Replaced in tests; every call is a bounded request with no retry.
accesstrade_transport = None
Merchant = Field(min_length=2, max_length=50, pattern=r'^[A-Za-z0-9 ._-]+$')


def _transport() -> dict:
    return {'transport': accesstrade_transport} if accesstrade_transport else {}


class ProductOut(BaseModel):
    product_id: str
    name: str
    url: str
    merchant: str
    price: int | None
    discount: int | None
    image: str | None


class ImportItem(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    product_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=8, max_length=2048)
    price: int | None = Field(default=None, gt=0, lt=10_000_000_000)
    discount: int | None = Field(default=None, gt=0, lt=10_000_000_000)


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    merchant: str = Merchant
    products: list[ImportItem] = Field(min_length=1, max_length=10)


class ImportResponse(BaseModel):
    program_id: UUID
    links: list[LinkResponse]
    skipped: list[str]


def _vnd(value: int) -> str:
    return f'{value:,}'.replace(',', '.') + 'đ'


@router.get('/campaigns/{campaign_id}/accesstrade/products', response_model=list[ProductOut])
def accesstrade_products(campaign_id: UUID, merchant: str = Query(min_length=2, max_length=50, pattern=r'^[A-Za-z0-9 ._-]+$'), limit: int = Query(default=20, ge=1, le=50),
                         db: Session = Depends(get_db)):
    _campaign(db, campaign_id)
    _, secret = active_secret(db, 'ACCESSTRADE')
    db.rollback()
    try:
        return [ProductOut(**vars(item)) for item in accesstrade.list_products(secret, merchant.strip().lower(), limit, **_transport())]
    except accesstrade.AccesstradeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from None
    except Exception:
        raise HTTPException(status_code=502, detail='ACCESSTRADE could not be reached') from None
    finally:
        secret = None


@router.post('/campaigns/{campaign_id}/accesstrade/import', response_model=ImportResponse, status_code=201)
def accesstrade_import(campaign_id: UUID, body: ImportRequest, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Create ACCESSTRADE tracking links for the chosen products and store product, price evidence and link."""
    path, payload = f'/api/v1/campaigns/{campaign_id}/accesstrade/import', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, ImportResponse):
        return existing
    _campaign(db, campaign_id, editable=True)
    for item in body.products:
        try:
            safe_url(item.url, https_only=True)
        except LinkRuleError:
            raise HTTPException(status_code=422, detail=f'Product URL is not a plain https address: {item.name}') from None
    _, secret = active_secret(db, 'ACCESSTRADE')
    merchant = body.merchant.lower()
    db.rollback()  # never hold a transaction while waiting on the network
    try:
        at_campaign = accesstrade.approved_campaign(secret, merchant, **_transport())
        created = accesstrade.create_links(secret, at_campaign, [item.url for item in body.products], f'c{str(campaign_id)[:8]}', **_transport())
    except accesstrade.AccesstradeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from None
    except Exception:
        raise HTTPException(status_code=502, detail='ACCESSTRADE could not be reached') from None
    finally:
        secret = None
    if existing := _idempotent(db, actor, key, 'POST', path, payload, ImportResponse):
        return existing
    by_origin = {link.url_origin: link.link for link in created}
    hosts = sorted({urlsplit(link).hostname for link in by_origin.values() if HOST_NAME.match(urlsplit(link).hostname or '')})
    if not hosts:
        raise HTTPException(status_code=502, detail='ACCESSTRADE did not return any tracking link')
    _campaign(db, campaign_id, lock=True, editable=True)
    name = f'ACCESSTRADE · {merchant}'
    program = db.scalar(select(AffiliateProgram).where(AffiliateProgram.campaign_id == campaign_id, AffiliateProgram.network == 'ACCESSTRADE', AffiliateProgram.name == name).with_for_update())
    if program is None:
        program = AffiliateProgram(campaign_id=campaign_id, network='ACCESSTRADE', name=name, join_url=None, link_hosts=hosts, tracking_param_keys=[], created_by=actor)
        db.add(program)
    else:
        program.link_hosts = sorted(set(program.link_hosts) | set(hosts))
    db.flush()
    now = datetime.now(UTC)
    links, skipped = [], []
    for item in body.products:
        tracking = by_origin.get(item.url)
        if tracking is None or urlsplit(tracking).hostname not in program.link_hosts:
            skipped.append(item.name)
            continue
        if db.scalar(select(AffiliateLink.id).where(AffiliateLink.campaign_id == campaign_id, AffiliateLink.final_url == tracking, AffiliateLink.status == 'ACTIVE')):
            skipped.append(item.name)
            continue
        price = item.discount or item.price
        source = None
        if price:
            text = f'{item.name}: giá {_vnd(price)}' + (f' (giá gốc {_vnd(item.price)})' if item.discount and item.price and item.price != item.discount else '')
            source = CampaignSource(campaign_id=campaign_id, source_name=f'ACCESSTRADE datafeed · {merchant}', source_url=item.url, excerpt=f'{text}. Dữ liệu ACCESSTRADE lúc {now:%d/%m/%Y %H:%M} UTC.',
                                    captured_at=now, verification_status='VERIFIED', verified_by=actor, verified_at=now,
                                    verification_note='Owner imported this price from the ACCESSTRADE API; prices can change.')
            db.add(source)
            db.flush()
        product = CampaignProduct(campaign_id=campaign_id, name=item.name, merchant=merchant, product_url=item.url, price_text=_vnd(price) if price else None,
                                  price_source_id=source.id if source else None, notes=f'ACCESSTRADE product {item.product_id}', created_by=actor)
        db.add(product)
        db.flush()
        link = AffiliateLink(campaign_id=campaign_id, program_id=program.id, product_id=product.id, label=item.name[:200], original_url=tracking, tracking_params={},
                             final_url=tracking, status='ACTIVE', created_by=actor)
        db.add(link)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail='A link changed during import; run it again') from None
        links.append(link)
    _audit(db, actor, 'campaign.accesstrade_imported', 'affiliate_program', program.id, campaign_id=campaign_id, merchant=merchant, link_hosts=program.link_hosts,
           created=len(links), skipped=len(skipped))
    result = ImportResponse(program_id=program.id, links=[LinkResponse.model_validate(link) for link in links], skipped=skipped)
    return _save(db, actor, key, 'POST', path, payload, result, 201, response, ImportResponse)


# Standing attestations ----------------------------------------------------------

class AttestationIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    check_name: Literal['MEDIA_RIGHTS', 'LEGAL_ADS_TAX']
    note: str = Field(min_length=3, max_length=1000)


class AttestationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    check_name: str
    note: str
    attested_by: str
    attested_at: datetime


class AttestationList(BaseModel):
    items: list[AttestationOut]


@router.get('/campaigns/{campaign_id}/attestations', response_model=list[AttestationOut])
def list_attestations(campaign_id: UUID, db: Session = Depends(get_db)):
    _campaign(db, campaign_id)
    return list(db.scalars(select(CampaignAttestation).where(CampaignAttestation.campaign_id == campaign_id, CampaignAttestation.revoked_at.is_(None))
                           .order_by(CampaignAttestation.check_name)))


@router.post('/campaigns/{campaign_id}/attestations', response_model=AttestationOut, status_code=201)
def attest_campaign(campaign_id: UUID, body: AttestationIn, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path, payload = f'/api/v1/campaigns/{campaign_id}/attestations', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, AttestationOut):
        return existing
    _campaign(db, campaign_id, lock=True, editable=True)
    now = datetime.now(UTC)
    for previous in db.scalars(select(CampaignAttestation).where(CampaignAttestation.campaign_id == campaign_id, CampaignAttestation.check_name == body.check_name,
                                                                 CampaignAttestation.revoked_at.is_(None)).with_for_update()):
        previous.revoked_at = now
    db.flush()
    row = CampaignAttestation(campaign_id=campaign_id, check_name=body.check_name, note=body.note, attested_by=actor, attested_at=now)
    db.add(row)
    db.flush()
    _audit(db, actor, 'campaign.attested', 'campaign', campaign_id, check=body.check_name)
    return _save(db, actor, key, 'POST', path, payload, AttestationOut.model_validate(row), 201, response, AttestationOut)


@router.post('/campaigns/{campaign_id}/attestations/{check_name}/revoke', response_model=AttestationList)
def revoke_attestation(campaign_id: UUID, check_name: Literal['MEDIA_RIGHTS', 'LEGAL_ADS_TAX'], response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner),
                       db: Session = Depends(get_db)):
    path = f'/api/v1/campaigns/{campaign_id}/attestations/{check_name}/revoke'
    if existing := _idempotent(db, actor, key, 'POST', path, {}, AttestationList):
        return existing
    _campaign(db, campaign_id, lock=True, editable=True)
    for row in db.scalars(select(CampaignAttestation).where(CampaignAttestation.campaign_id == campaign_id, CampaignAttestation.check_name == check_name,
                                                            CampaignAttestation.revoked_at.is_(None)).with_for_update()):
        row.revoked_at = datetime.now(UTC)
    db.flush()
    _audit(db, actor, 'campaign.attestation_revoked', 'campaign', campaign_id, check=check_name)
    rows = list(db.scalars(select(CampaignAttestation).where(CampaignAttestation.campaign_id == campaign_id, CampaignAttestation.revoked_at.is_(None))))
    return _save(db, actor, key, 'POST', path, {}, AttestationList(items=[AttestationOut.model_validate(row) for row in rows]), 200, response, AttestationList)


# Proposals -----------------------------------------------------------------------

class ProposalOut(BaseModel):
    content_id: UUID
    campaign_id: UUID
    campaign_name: str
    content_type: str
    title: str
    body: str
    hashtags: list[str]
    cta: str
    link_label: str | None
    ready: bool
    open_checks: list[str]
    created_at: datetime


@router.get('/proposals', response_model=list[ProposalOut])
def proposals(db: Session = Depends(get_db)):
    """Items in review in active campaigns: ready ones (every check passed) first."""
    rows = db.execute(select(ContentItem, Campaign, ContentVersion).join(Campaign, Campaign.id == ContentItem.campaign_id)
                      .join(ContentVersion, (ContentVersion.content_id == ContentItem.id) & (ContentVersion.version_no == ContentItem.current_version_no))
                      .where(ContentItem.status == 'IN_REVIEW', Campaign.status == 'ACTIVE').order_by(ContentItem.created_at, ContentItem.id).limit(200)).all()
    result = []
    for item, campaign, version in rows:
        pending = open_checks(db, item)
        link = db.get(AffiliateLink, item.affiliate_link_id)
        result.append(ProposalOut(content_id=item.id, campaign_id=campaign.id, campaign_name=campaign.name, content_type=item.content_type, title=version.title, body=version.body,
                                  hashtags=version.hashtags, cta=version.cta, link_label=link.label if link else None, ready=not pending, open_checks=pending, created_at=item.created_at))
    return sorted(result, key=lambda proposal: not proposal.ready)
