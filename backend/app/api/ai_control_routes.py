"""Owner global AI consent; separate approvals remain necessary for each run."""
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.opportunity_routes import _commit_or_conflict, _idempotent, _store_idempotency
from app.approvals.service import consume_action_authorization, evaluate_policy
from app.auth.dependencies import require_owner
from app.core.action_hash import action_hash, canonical_action
from app.db.models import AIExecutionControl, ActionAuthorization, ApprovalRequest, AuditEvent, Policy
from app.db.session import get_db

router = APIRouter(prefix='/api/v1/ai/control', dependencies=[Depends(require_owner)], tags=['ai-control'])


class ControlResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    enabled: bool
    version: int
    updated_at: datetime
    # Consent makes per-task execution requestable; each task still needs its own
    # approval, budget reservation, verified adapter and execution-enabled prompt.
    execution_available: bool = False

    @model_validator(mode='after')
    def derive_availability(self):
        self.execution_available = self.enabled
        return self


class EnableAction(BaseModel):
    action: dict[str, Any]
    action_hash: str


class EnableRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    policy_id: UUID
    approval_id: UUID


def _control(db: Session, lock: bool = False) -> AIExecutionControl:
    statement = select(AIExecutionControl).where(AIExecutionControl.name == 'primary')
    if lock:
        statement = statement.with_for_update()
    result = db.scalar(statement)
    if result is None:
        raise HTTPException(status_code=503, detail='AI control unavailable')
    return result


def _policy(db: Session, policy_id: UUID, lock: bool = False) -> Policy:
    statement = select(Policy).where(Policy.id == policy_id)
    if lock:
        statement = statement.with_for_update()
    policy = db.scalar(statement)
    allowed, _ = evaluate_policy(policy, 'AI_CONTROL_ENABLE')
    if not allowed or policy is None or policy.rules_json.get('external_execution') is not False or policy.rules_json.get('ai_inference_allowed') is not True:
        raise HTTPException(status_code=403, detail='AI control policy is unavailable or denies enabling')
    return policy


def _action(control: AIExecutionControl, policy: Policy) -> EnableAction:
    if control.enabled:
        raise HTTPException(status_code=409, detail='AI consent is already enabled')
    action = canonical_action('AI_CONTROL_ENABLE', {'control_version': control.version, 'enabled': True},
                              'ai_execution_control', control.id, policy.id, policy.version, 'ONCE')
    return EnableAction(action=action, action_hash=action_hash(action))


@router.get('', response_model=ControlResponse)
def get_control(db: Session = Depends(get_db)):
    return ControlResponse.model_validate(_control(db))


@router.get('/enable-action', response_model=EnableAction)
def prepare_enable(policy_id: UUID, db: Session = Depends(get_db)):
    return _action(_control(db), _policy(db, policy_id))


@router.post('/enable', response_model=ControlResponse)
def enable(body: EnableRequest, response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path, payload = '/api/v1/ai/control/enable', body.model_dump(mode='json')
    existing = _idempotent(db, actor, key, 'POST', path, payload, ControlResponse)
    if existing:
        return existing
    control = _control(db, lock=True)
    policy = _policy(db, body.policy_id, lock=True)
    expected = _action(control, policy)
    approval = db.scalar(select(ApprovalRequest).where(ApprovalRequest.id == body.approval_id).with_for_update())
    authorization = db.scalar(select(ActionAuthorization).where(ActionAuthorization.approval_id == body.approval_id).with_for_update())
    if approval is None or approval.policy_id != policy.id or authorization is None or not consume_action_authorization(db, authorization.id, expected.action_hash, actor):
        raise HTTPException(status_code=403, detail='Approval missing, expired, consumed or mismatched')
    control.enabled = True
    control.version += 1
    db.flush()
    result = ControlResponse.model_validate(control)
    db.add(AuditEvent(actor=actor, action='ai_control.enabled', entity_type='ai_execution_control', entity_id=control.id, detail={'approval_id': str(approval.id), 'version': control.version}))
    _store_idempotency(db, actor, key, 'POST', path, payload, result, 200)
    return _commit_or_conflict(db, actor, key, 'POST', path, payload, ControlResponse, response) or result


@router.post('/disable', response_model=ControlResponse)
def disable(response: Response, key: str = Header(alias='Idempotency-Key', min_length=1, max_length=255), actor: str = Depends(require_owner), db: Session = Depends(get_db)):
    path = '/api/v1/ai/control/disable'
    existing = _idempotent(db, actor, key, 'POST', path, {}, ControlResponse)
    if existing:
        return existing
    control = _control(db, lock=True)
    control.enabled = False
    control.version += 1  # Invalidate any unconsumed approval prepared before disable.
    db.flush()
    result = ControlResponse.model_validate(control)
    db.add(AuditEvent(actor=actor, action='ai_control.disabled', entity_type='ai_execution_control', entity_id=control.id, detail={'version': control.version}))
    _store_idempotency(db, actor, key, 'POST', path, {}, result, 200)
    return _commit_or_conflict(db, actor, key, 'POST', path, {}, ControlResponse, response) or result
