"""Owner integrations: store accounts once (secret write-only) and check a connection on request.

Nothing here searches, posts or creates links; later steps use these accounts only through
their own approval-gated flows. A connection check is the only outbound request.
"""
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai_brain.credentials import CredentialUnavailable, credential_digest, decrypt_credential, encrypt_credential
from app.ai_brain.network import provider_request
from app.api.campaign_routes import IdempotencyKey, _audit, _save
from app.api.opportunity_routes import _idempotent
from app.auth.dependencies import require_owner
from app.db.models import Integration
from app.db.session import get_db
from app.integrations.kinds import KINDS, ConfigError

router = APIRouter(prefix='/api/v1/integrations', dependencies=[Depends(require_owner)], tags=['integrations'])
KindName = Literal['SEARCH_TAVILY', 'SEARCH_BRAVE', 'ACCESSTRADE', 'FACEBOOK_PAGE']

# Replaced in tests; a single bounded request with no retry and no redirect.
connection_transport = provider_request


class IntegrationCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kind: KindName
    label: str = Field(min_length=1, max_length=100)
    config: dict[str, Any] = Field(default_factory=dict)
    secret: SecretStr


class IntegrationUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    label: str | None = Field(default=None, min_length=1, max_length=100)
    config: dict[str, Any] | None = None
    secret: SecretStr | None = None
    enabled: bool | None = None


class IntegrationResponse(BaseModel):
    id: UUID
    kind: str
    label: str
    purpose: str
    config: dict[str, Any]
    has_secret: bool
    enabled: bool
    check_costs: bool
    last_checked_at: datetime | None
    last_check_status: str | None
    last_check_detail: str | None
    created_at: datetime
    updated_at: datetime


def _response(item: Integration) -> IntegrationResponse:
    kind = KINDS[item.kind]
    return IntegrationResponse(id=item.id, kind=item.kind, label=item.label, purpose=kind.purpose, config=dict(item.config_json or {}), has_secret=item.encrypted_secret is not None,
                               enabled=item.enabled, check_costs=kind.check_costs, last_checked_at=item.last_checked_at, last_check_status=item.last_check_status,
                               last_check_detail=item.last_check_detail, created_at=item.created_at, updated_at=item.updated_at)


def _secret(value: SecretStr) -> str:
    secret = value.get_secret_value().strip()
    if not secret or len(secret) > 4096 or any(ord(char) < 33 or ord(char) == 127 for char in secret):
        raise HTTPException(status_code=422, detail='The token is empty, too long or contains spaces')
    return secret


def _digest(secret: str) -> str:
    try:
        return credential_digest(secret)
    except (CredentialUnavailable, UnicodeError):
        raise HTTPException(status_code=503, detail='Credential encryption is unavailable') from None


def _encrypt(item_id: UUID, secret: str) -> str:
    try:
        return encrypt_credential(item_id, secret)
    except (CredentialUnavailable, UnicodeError):
        raise HTTPException(status_code=503, detail='Credential encryption is unavailable') from None


def _clean(kind: str, config: dict[str, Any]) -> dict[str, Any]:
    try:
        return KINDS[kind].clean(config)
    except ConfigError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None


def _get(db: Session, item_id: UUID, *, lock: bool = False) -> Integration:
    statement = select(Integration).where(Integration.id == item_id, Integration.archived.is_(False))
    item = db.scalar(statement.with_for_update() if lock else statement)
    if item is None:
        raise HTTPException(status_code=404, detail='Integration not found')
    return item


def active_secret(db: Session, kind: str) -> tuple[Integration, str]:
    """For later steps: the enabled integration of a kind and its decrypted secret."""
    item = db.scalar(select(Integration).where(Integration.kind == kind, Integration.archived.is_(False), Integration.enabled.is_(True))
                     .order_by(Integration.created_at, Integration.id).limit(1))
    if item is None or item.encrypted_secret is None:
        raise HTTPException(status_code=409, detail=f'Connect {kind} on the Integrations page first')
    try:
        return item, decrypt_credential(item.id, item.encrypted_secret)
    except CredentialUnavailable:
        raise HTTPException(status_code=503, detail='Credential encryption is unavailable') from None


@router.get('', response_model=list[IntegrationResponse])
def list_integrations(db: Session = Depends(get_db)):
    rows = db.scalars(select(Integration).where(Integration.archived.is_(False)).order_by(Integration.kind, Integration.created_at, Integration.id))
    return [_response(row) for row in rows]


@router.post('', response_model=IntegrationResponse, status_code=201)
def create_integration(body: IntegrationCreate, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    secret = _secret(body.secret)
    config = _clean(body.kind, body.config)
    path = '/api/v1/integrations'
    payload = {'kind': body.kind, 'label': body.label, 'config': config, 'secret_digest': _digest(secret)}
    if existing := _idempotent(db, actor, key, 'POST', path, payload, IntegrationResponse):
        return existing
    item_id = uuid4()
    item = Integration(id=item_id, kind=body.kind, label=body.label, config_json=config, encrypted_secret=_encrypt(item_id, secret), enabled=True, archived=False, created_by=actor)
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='An integration of this kind already uses that name') from None
    _audit(db, actor, 'integration.created', 'integration', item.id, kind=item.kind, config_keys=sorted(config))
    return _save(db, actor, key, 'POST', path, payload, _response(item), 201, response, IntegrationResponse)


@router.patch('/{item_id}', response_model=IntegrationResponse)
def update_integration(item_id: UUID, body: IntegrationUpdate, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    secret = _secret(body.secret) if body.secret is not None else None
    path = f'/api/v1/integrations/{item_id}'
    payload = body.model_dump(mode='json', exclude_unset=True, exclude={'secret'}) | {'secret_digest': _digest(secret) if secret else None}
    if existing := _idempotent(db, actor, key, 'PATCH', path, payload, IntegrationResponse):
        return existing
    item = _get(db, item_id, lock=True)
    changed = []
    if body.label is not None:
        item.label, changed = body.label, [*changed, 'label']
    if body.config is not None:
        item.config_json, changed = _clean(item.kind, body.config), [*changed, 'config']
    if body.enabled is not None:
        item.enabled, changed = body.enabled, [*changed, 'enabled']
    if secret is not None:
        item.encrypted_secret, changed = _encrypt(item.id, secret), [*changed, 'secret']
    if secret is not None or body.config is not None:
        item.last_checked_at = item.last_check_status = item.last_check_detail = None  # a new account must be checked again
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='An integration of this kind already uses that name') from None
    _audit(db, actor, 'integration.updated', 'integration', item.id, fields=changed)
    return _save(db, actor, key, 'PATCH', path, payload, _response(item), 200, response, IntegrationResponse)


@router.post('/{item_id}/archive', response_model=IntegrationResponse)
def archive_integration(item_id: UUID, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Remove the account: the encrypted secret is deleted and cannot be recovered."""
    path = f'/api/v1/integrations/{item_id}/archive'
    if existing := _idempotent(db, actor, key, 'POST', path, {}, IntegrationResponse):
        return existing
    item = _get(db, item_id, lock=True)
    item.encrypted_secret, item.enabled, item.archived = None, False, True
    db.flush()
    _audit(db, actor, 'integration.archived', 'integration', item.id, kind=item.kind)
    return _save(db, actor, key, 'POST', path, {}, _response(item), 200, response, IntegrationResponse)


@router.post('/{item_id}/test', response_model=IntegrationResponse)
def test_integration(item_id: UUID, response: Response, key: str = IdempotencyKey, actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """One request to the official host. Search checks use one paid query; the others are free reads."""
    path = f'/api/v1/integrations/{item_id}/test'
    if existing := _idempotent(db, actor, key, 'POST', path, {}, IntegrationResponse):
        return existing
    item = _get(db, item_id)
    if item.encrypted_secret is None:
        raise HTTPException(status_code=409, detail='The token is not configured')
    kind, config, ciphertext = KINDS[item.kind], dict(item.config_json or {}), item.encrypted_secret
    try:
        secret = decrypt_credential(item.id, ciphertext)
    except CredentialUnavailable:
        raise HTTPException(status_code=503, detail='Credential encryption is unavailable') from None
    db.rollback()  # never hold a transaction while waiting on the network
    detail = None
    try:
        request = kind.check(config, secret)
        code, raw = connection_transport(request.method, request.url, {kind.host}, request.headers, request.payload, 20, query=request.query)
        if code in (401, 403):
            outcome = 'AUTH_FAILED'
        elif code == 429:
            outcome = 'RATE_LIMITED'
        elif not 200 <= code < 300:
            outcome = 'PROVIDER_ERROR'
        else:
            detail = kind.verify(config, raw)
            outcome = 'OK' if detail else 'INVALID_RESPONSE'
    except Exception:
        outcome = 'UNREACHABLE'
    finally:
        secret = None
    item = _get(db, item_id, lock=True)
    if item.encrypted_secret != ciphertext or dict(item.config_json or {}) != config:
        raise HTTPException(status_code=409, detail='The integration changed during the check; run it again')
    item.last_checked_at, item.last_check_status, item.last_check_detail = datetime.now(UTC), outcome, detail
    db.flush()
    _audit(db, actor, 'integration.checked', 'integration', item.id, kind=item.kind, outcome=outcome)
    return _save(db, actor, key, 'POST', path, {}, _response(item), 200, response, IntegrationResponse)
