"""Step 7A campaigns: Owner-managed products, affiliate programs, terms, sources and links.

Level B only. The server never opens a source, product or affiliate URL, never publishes
and never pays. Every change is idempotent and audited.
"""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.campaign_schemas import (
    CampaignCreate, CampaignResponse, CampaignStatusChange, CampaignUpdate, LinkCreate, LinkResponse, ProductCreate, ProductResponse,
    ProgramCreate, ProgramResponse, SourceCreate, SourceResponse, SourceVerification, TermCreate, TermResponse,
)
from app.api.opportunity_routes import _idempotent, _store_idempotency
from app.auth.dependencies import require_owner
from app.campaigns.links import LinkRuleError, compose
from app.db.models import AffiliateLink, AffiliateProgram, AffiliateProgramTerm, AIResearchRun, AuditEvent, Campaign, CampaignProduct, CampaignSource, Opportunity
from app.db.session import get_db

router = APIRouter(prefix='/api/v1/campaigns', dependencies=[Depends(require_owner)], tags=['campaigns'])
IdempotencyKey = Header(alias='Idempotency-Key', min_length=1, max_length=255)
TRANSITIONS = {'DRAFT': {'ACTIVE', 'ARCHIVED'}, 'ACTIVE': {'PAUSED', 'ARCHIVED'}, 'PAUSED': {'ACTIVE', 'ARCHIVED'}, 'ARCHIVED': set()}
CLOCK_SKEW = timedelta(minutes=5)


def _campaign(db: Session, campaign_id: UUID, *, lock: bool = False, editable: bool = False) -> Campaign:
    statement = select(Campaign).where(Campaign.id == campaign_id)
    campaign = db.scalar(statement.with_for_update() if lock else statement)
    if campaign is None:
        raise HTTPException(status_code=404, detail='Campaign not found')
    if editable and campaign.status == 'ARCHIVED':
        raise HTTPException(status_code=409, detail='Archived campaigns are read-only')
    return campaign


def _source(db: Session, campaign_id: UUID, source_id: UUID | None) -> CampaignSource | None:
    if source_id is None:
        return None
    source = db.scalar(select(CampaignSource).where(CampaignSource.id == source_id, CampaignSource.campaign_id == campaign_id))
    if source is None:
        raise HTTPException(status_code=422, detail='Source does not belong to this campaign')
    if source.verification_status == 'REJECTED':
        raise HTTPException(status_code=409, detail='A rejected source cannot support campaign data')
    return source


def _evidence(source: CampaignSource | None) -> str:
    return 'UNSOURCED' if source is None else source.verification_status


def _save(db: Session, actor: str, key: str, method: str, path: str, payload: dict[str, Any], result: Any, code: int, response: Response, schema: Any) -> Any:
    """Store the idempotent response and commit; a concurrent replay returns the stored result."""
    _store_idempotency(db, actor, key, method, path, payload, result, code)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _idempotent(db, actor, key, method, path, payload, schema)
        if existing is None:
            raise HTTPException(status_code=409, detail='Request conflicts with existing campaign data') from None
        response.status_code = code
        return existing
    return result


def _flush(db: Session, detail: str) -> None:
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from None


def _audit(db: Session, actor: str, action: str, entity_type: str, entity_id: UUID, **detail: Any) -> None:
    db.add(AuditEvent(actor=actor, action=action, entity_type=entity_type, entity_id=entity_id, detail={k: str(v) if isinstance(v, UUID) else v for k, v in detail.items()}))


# Campaigns -----------------------------------------------------------------

@router.get('', response_model=list[CampaignResponse])
def list_campaigns(status: str | None = None, limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    statement = select(Campaign)
    if status:
        if status not in TRANSITIONS:
            raise HTTPException(status_code=422, detail='Invalid campaign status')
        statement = statement.where(Campaign.status == status)
    return list(db.scalars(statement.order_by(Campaign.created_at.desc(), Campaign.id).offset(offset).limit(limit)))


@router.post('', response_model=CampaignResponse, status_code=201)
def create_campaign(body: CampaignCreate, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path, payload = '/api/v1/campaigns', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, CampaignResponse):
        return existing
    opportunity = db.scalar(select(Opportunity).where(Opportunity.id == body.opportunity_id).with_for_update())
    if opportunity is None:
        raise HTTPException(status_code=404, detail='Opportunity not found')
    if opportunity.status != 'EVALUATED':
        raise HTTPException(status_code=409, detail='Only an evaluated opportunity can start a campaign')
    campaign = Campaign(**body.model_dump(), business_model=opportunity.business_model, status='DRAFT', version=1, created_by=actor)
    db.add(campaign)
    db.flush()
    _audit(db, actor, 'campaign.created', 'campaign', campaign.id, opportunity_id=opportunity.id, max_cost_usd=str(campaign.max_cost_usd))
    return _save(db, actor, key, 'POST', path, payload, CampaignResponse.model_validate(campaign), 201, response, CampaignResponse)


@router.get('/{campaign_id}', response_model=CampaignResponse)
def get_campaign(campaign_id: UUID, db: Session = Depends(get_db)):
    return _campaign(db, campaign_id)


@router.patch('/{campaign_id}', response_model=CampaignResponse)
def update_campaign(campaign_id: UUID, body: CampaignUpdate, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path, payload = f'/api/v1/campaigns/{campaign_id}', body.model_dump(mode='json', exclude_unset=True)
    if existing := _idempotent(db, actor, key, 'PATCH', path, payload, CampaignResponse):
        return existing
    campaign = _campaign(db, campaign_id, lock=True, editable=True)
    if campaign.version != body.version:
        raise HTTPException(status_code=409, detail='Campaign changed; reload and retry')
    changes = body.model_dump(exclude_unset=True, exclude={'version'})
    for required in ('name', 'language', 'max_cost_usd'):
        if required in changes and changes[required] is None:
            raise HTTPException(status_code=422, detail=f'{required} cannot be empty')
    if 'max_cost_usd' in changes:
        committed = db.scalar(select(func.coalesce(func.sum(AIResearchRun.max_cost_usd), 0)).where(AIResearchRun.campaign_id == campaign.id, AIResearchRun.kind == 'CONTENT'))
        if Decimal(changes['max_cost_usd']) < Decimal(committed):
            raise HTTPException(status_code=409, detail=f'The AI cost limit cannot be below the {committed} USD already allocated to content batches')
    if changes.get('disclosure_text') == '':
        changes['disclosure_text'] = None
    for field, value in changes.items():
        setattr(campaign, field, value)
    campaign.version += 1
    db.flush()
    _audit(db, actor, 'campaign.updated', 'campaign', campaign.id, fields=sorted(changes), version=campaign.version)
    return _save(db, actor, key, 'PATCH', path, payload, CampaignResponse.model_validate(campaign), 200, response, CampaignResponse)


@router.post('/{campaign_id}/status', response_model=CampaignResponse)
def change_status(campaign_id: UUID, body: CampaignStatusChange, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path, payload = f'/api/v1/campaigns/{campaign_id}/status', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, CampaignResponse):
        return existing
    campaign = _campaign(db, campaign_id, lock=True)
    if campaign.version != body.version:
        raise HTTPException(status_code=409, detail='Campaign changed; reload and retry')
    if body.status not in TRANSITIONS[campaign.status]:
        raise HTTPException(status_code=409, detail=f'Cannot change a {campaign.status} campaign to {body.status}')
    previous, campaign.status = campaign.status, body.status
    campaign.version += 1
    db.flush()
    _audit(db, actor, 'campaign.status_changed', 'campaign', campaign.id, previous=previous, status=body.status)
    return _save(db, actor, key, 'POST', path, payload, CampaignResponse.model_validate(campaign), 200, response, CampaignResponse)


# Sources -------------------------------------------------------------------

@router.get('/{campaign_id}/sources', response_model=list[SourceResponse])
def list_sources(campaign_id: UUID, limit: int = Query(default=100, ge=1, le=200), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    _campaign(db, campaign_id)
    return list(db.scalars(select(CampaignSource).where(CampaignSource.campaign_id == campaign_id).order_by(CampaignSource.created_at, CampaignSource.id).offset(offset).limit(limit)))


@router.post('/{campaign_id}/sources', response_model=SourceResponse, status_code=201)
def add_source(campaign_id: UUID, body: SourceCreate, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path, payload = f'/api/v1/campaigns/{campaign_id}/sources', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, SourceResponse):
        return existing
    _campaign(db, campaign_id, lock=True, editable=True)
    if body.captured_at > datetime.now(UTC) + CLOCK_SKEW:
        raise HTTPException(status_code=422, detail='captured_at cannot be in the future')
    source = CampaignSource(campaign_id=campaign_id, **body.model_dump(), verification_status='UNVERIFIED')
    db.add(source)
    db.flush()
    _audit(db, actor, 'campaign.source_added', 'campaign_source', source.id, campaign_id=campaign_id)
    return _save(db, actor, key, 'POST', path, payload, SourceResponse.model_validate(source), 201, response, SourceResponse)


@router.post('/{campaign_id}/sources/{source_id}/verification', response_model=SourceResponse)
def verify_source(campaign_id: UUID, source_id: UUID, body: SourceVerification, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """The Owner's own judgement of an excerpt. It is final; the server never opens the URL."""
    path, payload = f'/api/v1/campaigns/{campaign_id}/sources/{source_id}/verification', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, SourceResponse):
        return existing
    _campaign(db, campaign_id, lock=True, editable=True)
    source = db.scalar(select(CampaignSource).where(CampaignSource.id == source_id, CampaignSource.campaign_id == campaign_id).with_for_update())
    if source is None:
        raise HTTPException(status_code=404, detail='Source not found')
    if source.verification_status != 'UNVERIFIED':
        raise HTTPException(status_code=409, detail='Source decision is final')
    source.verification_status, source.verified_by, source.verified_at, source.verification_note = body.status, actor, datetime.now(UTC), body.note
    db.flush()
    _audit(db, actor, 'campaign.source_verified' if body.status == 'VERIFIED' else 'campaign.source_rejected', 'campaign_source', source.id, campaign_id=campaign_id)
    return _save(db, actor, key, 'POST', path, payload, SourceResponse.model_validate(source), 200, response, SourceResponse)


# Affiliate programs and terms ----------------------------------------------

def _term_response(db: Session, term: AffiliateProgramTerm) -> TermResponse:
    source = db.get(CampaignSource, term.source_id) if term.source_id else None
    return TermResponse.model_validate({**{c: getattr(term, c) for c in ('id', 'program_id', 'term', 'value_text', 'value_numeric', 'unit', 'source_id', 'created_by', 'created_at')}, 'evidence_status': _evidence(source)})


def _program_response(db: Session, program: AffiliateProgram) -> ProgramResponse:
    terms = db.scalars(select(AffiliateProgramTerm).where(AffiliateProgramTerm.program_id == program.id).order_by(AffiliateProgramTerm.term, AffiliateProgramTerm.created_at, AffiliateProgramTerm.id))
    fields = {c: getattr(program, c) for c in ('id', 'campaign_id', 'network', 'name', 'join_url', 'link_hosts', 'tracking_param_keys', 'created_by', 'created_at')}
    return ProgramResponse.model_validate({**fields, 'terms': [_term_response(db, term) for term in terms]})


@router.get('/{campaign_id}/programs', response_model=list[ProgramResponse])
def list_programs(campaign_id: UUID, db: Session = Depends(get_db)):
    _campaign(db, campaign_id)
    programs = db.scalars(select(AffiliateProgram).where(AffiliateProgram.campaign_id == campaign_id).order_by(AffiliateProgram.created_at, AffiliateProgram.id).limit(50))
    return [_program_response(db, program) for program in programs]


@router.post('/{campaign_id}/programs', response_model=ProgramResponse, status_code=201)
def add_program(campaign_id: UUID, body: ProgramCreate, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path, payload = f'/api/v1/campaigns/{campaign_id}/programs', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, ProgramResponse):
        return existing
    _campaign(db, campaign_id, lock=True, editable=True)
    program = AffiliateProgram(campaign_id=campaign_id, **body.model_dump(), created_by=actor)
    db.add(program)
    _flush(db, 'This campaign already has a program with that network and name')
    _audit(db, actor, 'campaign.program_added', 'affiliate_program', program.id, campaign_id=campaign_id, network=program.network)
    return _save(db, actor, key, 'POST', path, payload, _program_response(db, program), 201, response, ProgramResponse)


@router.post('/{campaign_id}/programs/{program_id}/terms', response_model=TermResponse, status_code=201)
def add_term(campaign_id: UUID, program_id: UUID, body: TermCreate, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Terms are append-only: a newer row for the same term supersedes the older one."""
    path, payload = f'/api/v1/campaigns/{campaign_id}/programs/{program_id}/terms', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, TermResponse):
        return existing
    _campaign(db, campaign_id, lock=True, editable=True)
    if db.scalar(select(AffiliateProgram.id).where(AffiliateProgram.id == program_id, AffiliateProgram.campaign_id == campaign_id)) is None:
        raise HTTPException(status_code=404, detail='Affiliate program not found')
    _source(db, campaign_id, body.source_id)
    term = AffiliateProgramTerm(campaign_id=campaign_id, program_id=program_id, **body.model_dump(), created_by=actor)
    db.add(term)
    _flush(db, 'Request conflicts with existing campaign data')
    _audit(db, actor, 'campaign.term_recorded', 'affiliate_program_term', term.id, program_id=program_id, term=term.term, source_id=term.source_id)
    return _save(db, actor, key, 'POST', path, payload, _term_response(db, term), 201, response, TermResponse)


# Products ------------------------------------------------------------------

def _product_response(db: Session, product: CampaignProduct) -> ProductResponse:
    source = db.get(CampaignSource, product.price_source_id) if product.price_source_id else None
    fields = {c: getattr(product, c) for c in ('id', 'campaign_id', 'name', 'merchant', 'product_url', 'price_text', 'price_source_id', 'notes', 'created_by', 'created_at')}
    return ProductResponse.model_validate({**fields, 'price_evidence_status': _evidence(source)})


@router.get('/{campaign_id}/products', response_model=list[ProductResponse])
def list_products(campaign_id: UUID, db: Session = Depends(get_db)):
    _campaign(db, campaign_id)
    products = db.scalars(select(CampaignProduct).where(CampaignProduct.campaign_id == campaign_id).order_by(CampaignProduct.created_at, CampaignProduct.id).limit(200))
    return [_product_response(db, product) for product in products]


@router.post('/{campaign_id}/products', response_model=ProductResponse, status_code=201)
def add_product(campaign_id: UUID, body: ProductCreate, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path, payload = f'/api/v1/campaigns/{campaign_id}/products', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, ProductResponse):
        return existing
    _campaign(db, campaign_id, lock=True, editable=True)
    _source(db, campaign_id, body.price_source_id)
    product = CampaignProduct(campaign_id=campaign_id, **body.model_dump(), created_by=actor)
    db.add(product)
    _flush(db, 'Request conflicts with existing campaign data')
    _audit(db, actor, 'campaign.product_added', 'campaign_product', product.id, campaign_id=campaign_id)
    return _save(db, actor, key, 'POST', path, payload, _product_response(db, product), 201, response, ProductResponse)


# Affiliate links -----------------------------------------------------------

@router.get('/{campaign_id}/links', response_model=list[LinkResponse])
def list_links(campaign_id: UUID, db: Session = Depends(get_db)):
    _campaign(db, campaign_id)
    return list(db.scalars(select(AffiliateLink).where(AffiliateLink.campaign_id == campaign_id).order_by(AffiliateLink.created_at, AffiliateLink.id).limit(200)))


@router.post('/{campaign_id}/links', response_model=LinkResponse, status_code=201)
def add_link(campaign_id: UUID, body: LinkCreate, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Store an Owner-provided affiliate link. It is composed, never opened or shared."""
    path, payload = f'/api/v1/campaigns/{campaign_id}/links', body.model_dump(mode='json')
    if existing := _idempotent(db, actor, key, 'POST', path, payload, LinkResponse):
        return existing
    _campaign(db, campaign_id, lock=True, editable=True)
    program = db.scalar(select(AffiliateProgram).where(AffiliateProgram.id == body.program_id, AffiliateProgram.campaign_id == campaign_id))
    if program is None:
        raise HTTPException(status_code=404, detail='Affiliate program not found')
    if body.product_id and db.scalar(select(CampaignProduct.id).where(CampaignProduct.id == body.product_id, CampaignProduct.campaign_id == campaign_id)) is None:
        raise HTTPException(status_code=404, detail='Product not found')
    try:
        final_url = compose(body.original_url, program.link_hosts, program.tracking_param_keys, body.tracking_params)
    except LinkRuleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    link = AffiliateLink(campaign_id=campaign_id, program_id=program.id, product_id=body.product_id, label=body.label, original_url=body.original_url,
                         tracking_params=dict(sorted(body.tracking_params.items())), final_url=final_url, status='ACTIVE', created_by=actor)
    db.add(link)
    _flush(db, 'This campaign already has an active link with the same final URL')
    _audit(db, actor, 'campaign.link_added', 'affiliate_link', link.id, campaign_id=campaign_id, program_id=program.id)
    return _save(db, actor, key, 'POST', path, payload, LinkResponse.model_validate(link), 201, response, LinkResponse)


@router.post('/{campaign_id}/links/{link_id}/retire', response_model=LinkResponse)
def retire_link(campaign_id: UUID, link_id: UUID, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path, payload = f'/api/v1/campaigns/{campaign_id}/links/{link_id}/retire', {}
    if existing := _idempotent(db, actor, key, 'POST', path, payload, LinkResponse):
        return existing
    _campaign(db, campaign_id, lock=True, editable=True)
    link = db.scalar(select(AffiliateLink).where(AffiliateLink.id == link_id, AffiliateLink.campaign_id == campaign_id).with_for_update())
    if link is None:
        raise HTTPException(status_code=404, detail='Link not found')
    if link.status != 'ACTIVE':
        raise HTTPException(status_code=409, detail='Link is already retired')
    link.status, link.retired_at = 'RETIRED', datetime.now(UTC)
    db.flush()
    _audit(db, actor, 'campaign.link_retired', 'affiliate_link', link.id, campaign_id=campaign_id)
    return _save(db, actor, key, 'POST', path, payload, LinkResponse.model_validate(link), 200, response, LinkResponse)
