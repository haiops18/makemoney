"""Provider configuration and a zero-cost connection test. No endpoint here invokes a model."""
from datetime import UTC, datetime
from typing import Literal

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.ai_brain.adapters import adapter_for
from app.ai_brain.credentials import CredentialUnavailable, credential_digest, decrypt_credential, encrypt_credential
from app.ai_brain.network import get_provider_json
from app.api.ai_provider_schemas import ProviderCreate, ProviderResponse, ProviderUpdate
from app.api.opportunity_routes import _commit_or_conflict, _idempotent, _store_idempotency
from app.auth.dependencies import require_owner
from app.db.models import AIExecutionControl, AIProvider, AuditEvent
from app.db.session import get_db

router = APIRouter(prefix='/api/v1/ai/providers', dependencies=[Depends(require_owner)], tags=['ai-providers'])


def _response(provider: AIProvider) -> ProviderResponse:
    return ProviderResponse(
        id=provider.id, name=provider.name, kind=provider.kind, base_url=provider.base_url,
        default_model=provider.default_model, enabled=provider.enabled, archived=provider.archived, is_default=provider.is_default,
        has_api_key=provider.encrypted_api_key is not None, adapter_verified=adapter_for(provider.kind, provider.base_url) is not None,
        last_checked_at=provider.last_checked_at, last_check_status=provider.last_check_status, last_check_model_listed=provider.last_check_model_listed,
        created_at=provider.created_at, updated_at=provider.updated_at)


@router.get('', response_model=list[ProviderResponse])
def list_providers(limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    rows = db.scalars(select(AIProvider).where(AIProvider.archived.is_(False)).order_by(AIProvider.created_at, AIProvider.id).offset(offset).limit(limit))
    return [_response(row) for row in rows]


@router.post('', response_model=ProviderResponse, status_code=201)
def create_provider(body: ProviderCreate, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    secret = body.api_key.get_secret_value() if body.api_key is not None else None
    if secret is not None and (not secret or len(secret) > 4096):
        raise HTTPException(status_code=422, detail='Provider credential is invalid')
    try:
        fingerprint = credential_digest(secret) if secret is not None else None
    except (CredentialUnavailable, UnicodeError):
        raise HTTPException(status_code=503, detail='AI credential encryption is unavailable') from None
    payload = body.model_dump(mode='json', exclude={'api_key'}) | {'credential_digest': fingerprint}
    path = '/api/v1/ai/providers'
    existing = _idempotent(db, actor, key, 'POST', path, payload, ProviderResponse)
    if existing:
        return existing
    provider_id = uuid4()
    try:
        encrypted = encrypt_credential(provider_id, secret) if secret is not None else None
    except (CredentialUnavailable, UnicodeError):
        raise HTTPException(status_code=422, detail='Provider credential is invalid or encryption unavailable') from None
    provider = AIProvider(id=provider_id, name=body.name, kind=body.kind, base_url=body.base_url,
                          default_model=body.default_model, encrypted_api_key=encrypted, enabled=False, archived=False, is_default=False)
    db.add(provider)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Provider configuration conflicts with an existing record') from None
    result = _response(provider)
    db.add(AuditEvent(actor=actor, action='ai_provider.created', entity_type='ai_provider', entity_id=provider.id, detail={'kind': provider.kind, 'credential_configured': secret is not None}))
    _store_idempotency(db, actor, key, 'POST', path, payload, result, 201)
    return _commit_or_conflict(db, actor, key, 'POST', path, payload, ProviderResponse, response) or result


@router.patch('/{provider_id}', response_model=ProviderResponse)
def update_provider(provider_id: UUID, body: ProviderUpdate, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    secret = body.api_key.get_secret_value() if body.api_key is not None else None
    if secret is not None and (not secret or len(secret) > 4096 or body.revoke_api_key):
        raise HTTPException(status_code=422, detail='Invalid credential update')
    try:
        fingerprint = credential_digest(secret) if secret is not None else None
    except (CredentialUnavailable, UnicodeError):
        raise HTTPException(status_code=503, detail='AI credential encryption is unavailable') from None
    payload = body.model_dump(mode='json', exclude_unset=True, exclude={'api_key'}) | {'credential_digest': fingerprint}
    path = f'/api/v1/ai/providers/{provider_id}'
    existing = _idempotent(db, actor, key, 'PATCH', path, payload, ProviderResponse)
    if existing:
        return existing
    provider = db.scalar(select(AIProvider).where(AIProvider.id == provider_id, AIProvider.archived.is_(False)).with_for_update())
    if provider is None:
        raise HTTPException(status_code=404, detail='Provider not found')
    for field in ('name', 'base_url', 'default_model', 'enabled'):
        if field in body.model_fields_set:
            value = getattr(body, field)
            if field != 'base_url' and value is None:
                raise HTTPException(status_code=422, detail='Invalid provider update')
            setattr(provider, field, value)
    try:
        if secret is not None:
            provider.encrypted_api_key = encrypt_credential(provider.id, secret)
        elif body.revoke_api_key:
            provider.encrypted_api_key = None
            provider.enabled = False
    except (CredentialUnavailable, UnicodeError):
        raise HTTPException(status_code=503, detail='AI credential encryption is unavailable') from None
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Provider configuration conflicts with an existing record') from None
    result = _response(provider)
    db.add(AuditEvent(actor=actor, action='ai_provider.updated', entity_type='ai_provider', entity_id=provider.id,
                      detail={'fields': sorted(body.model_fields_set - {'api_key'}), 'credential_changed': secret is not None or body.revoke_api_key}))
    _store_idempotency(db, actor, key, 'PATCH', path, payload, result, 200)
    return _commit_or_conflict(db, actor, key, 'PATCH', path, payload, ProviderResponse, response) or result


@router.post('/{provider_id}/archive', response_model=ProviderResponse)
def archive_provider(provider_id: UUID, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path = f'/api/v1/ai/providers/{provider_id}/archive'
    existing = _idempotent(db, actor, key, 'POST', path, {}, ProviderResponse)
    if existing:
        return existing
    provider = db.scalar(select(AIProvider).where(AIProvider.id == provider_id, AIProvider.archived.is_(False)).with_for_update())
    if provider is None:
        raise HTTPException(status_code=404, detail='Provider not found')
    provider.archived = True
    provider.enabled = False
    provider.is_default = False
    db.flush()
    result = _response(provider)
    db.add(AuditEvent(actor=actor, action='ai_provider.archived', entity_type='ai_provider', entity_id=provider.id, detail={}))
    _store_idempotency(db, actor, key, 'POST', path, {}, result, 200)
    return _commit_or_conflict(db, actor, key, 'POST', path, {}, ProviderResponse, response) or result


@router.post('/{provider_id}/default', response_model=ProviderResponse)
def set_default(provider_id: UUID, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path = f'/api/v1/ai/providers/{provider_id}/default'
    existing = _idempotent(db, actor, key, 'POST', path, {}, ProviderResponse)
    if existing:
        return existing
    # Lock all configurations in a consistent order so concurrent choices cannot
    # both win, including when there is no existing default.
    rows = list(db.scalars(select(AIProvider).order_by(AIProvider.id).with_for_update()))
    provider = next((row for row in rows if row.id == provider_id and not row.archived), None)
    if provider is None:
        raise HTTPException(status_code=404, detail='Provider not found')
    for row in rows:
        if row.is_default and row.id != provider_id:
            row.is_default = False
    db.flush()
    provider.is_default = True
    db.flush()
    result = _response(provider)
    db.add(AuditEvent(actor=actor, action='ai_provider.default_selected', entity_type='ai_provider', entity_id=provider.id, detail={}))
    _store_idempotency(db, actor, key, 'POST', path, {}, result, 200)
    return _commit_or_conflict(db, actor, key, 'POST', path, {}, ProviderResponse, response) or result


# Replaced in tests; production always uses the pinned HTTPS transport.
connection_transport = get_provider_json
CheckStatus = Literal['OK', 'AUTH_FAILED', 'RATE_LIMITED', 'PROVIDER_ERROR', 'UNREACHABLE', 'INVALID_RESPONSE']


class ConnectionTestResponse(BaseModel):
    provider_id: str
    status: CheckStatus
    model_listed: bool | None
    checked_at: datetime


@router.post('/{provider_id}/connection-test', response_model=ConnectionTestResponse)
def test_connection(provider_id: UUID, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    """List models once on the official endpoint; this sends no prompt and incurs no inference.

    Requires global AI consent because it transmits the stored credential. The
    request is made without an open transaction and has no automatic retry.
    """
    path = f'/api/v1/ai/providers/{provider_id}/connection-test'
    existing = _idempotent(db, actor, key, 'POST', path, {}, ConnectionTestResponse)
    if existing:
        return existing
    provider = db.scalar(select(AIProvider).where(AIProvider.id == provider_id, AIProvider.archived.is_(False)))
    if provider is None:
        raise HTTPException(status_code=404, detail='Provider not found')
    control = db.scalar(select(AIExecutionControl).where(AIExecutionControl.name == 'primary'))
    if control is None or not control.enabled:
        raise HTTPException(status_code=403, detail='Global AI consent is disabled')
    adapter = adapter_for(provider.kind, provider.base_url)
    if adapter is None:
        raise HTTPException(status_code=403, detail='Provider adapter has not been verified for this endpoint')
    if not provider.encrypted_api_key:
        raise HTTPException(status_code=409, detail='Provider credential is not configured')
    ciphertext, model = provider.encrypted_api_key, provider.default_model
    try:
        credential = decrypt_credential(provider.id, ciphertext)
    except CredentialUnavailable:
        raise HTTPException(status_code=503, detail='AI credential encryption is unavailable') from None
    db.rollback()  # never hold a transaction or row lock while waiting on the network
    model_listed = None
    try:
        code, raw = connection_transport(adapter.models_url(), {adapter.host}, adapter.headers(credential), 15)
        if code in (401, 403):
            outcome = 'AUTH_FAILED'
        elif code == 429:
            outcome = 'RATE_LIMITED'
        elif not 200 <= code < 300:
            outcome = 'PROVIDER_ERROR'
        else:
            names = adapter.model_ids(raw)
            outcome = 'OK' if names is not None else 'INVALID_RESPONSE'
            model_listed = None if names is None else model in names
    except Exception:
        outcome = 'UNREACHABLE'
    finally:
        credential = None
    provider = db.scalar(select(AIProvider).where(AIProvider.id == provider_id).with_for_update())
    if provider is None or provider.encrypted_api_key != ciphertext:
        raise HTTPException(status_code=409, detail='Provider credential changed during the connection test')
    now = datetime.now(UTC)
    provider.last_checked_at, provider.last_check_status, provider.last_check_model_listed = now, outcome, model_listed
    result = ConnectionTestResponse(provider_id=str(provider.id), status=outcome, model_listed=model_listed, checked_at=now)
    db.add(AuditEvent(actor=actor, action='ai_provider.connection_tested', entity_type='ai_provider', entity_id=provider.id,
                      detail={'status': outcome, 'model_listed': model_listed}))
    _store_idempotency(db, actor, key, 'POST', path, {}, result, 200)
    return _commit_or_conflict(db, actor, key, 'POST', path, {}, ConnectionTestResponse, response) or result
