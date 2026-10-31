import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.approval_schemas import ApprovalCreate, ApprovalDecisionInput, ApprovalListResponse, ApprovalResponse, PolicyEvaluationRequest, PolicyEvaluationResponse, PolicyResponse
from app.approvals.service import evaluate_policy, is_expired
from app.auth.dependencies import require_owner
from app.core.action_hash import action_hash, canonical_action
from app.db.models import ActionAuthorization, ApprovalDecision, ApprovalRequest, AuditEvent, IdempotencyRecord, Policy
from app.db.session import get_db

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_owner)])
APPROVAL_STATUSES = {"PENDING", "APPROVED", "REJECTED", "EXPIRED", "CONSUMED"}


def _idempotency_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _existing_response(db: Session, actor: str, key: str, method: str, path: str, request_hash: str) -> ApprovalResponse | None:
    record = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.actor == actor, IdempotencyRecord.key == key))
    if record is None:
        return None
    if (record.method, record.path, record.request_hash) != (method, path, request_hash):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key was used for another request")
    return ApprovalResponse.model_validate(record.response_body)


def _action_for_request(request: PolicyEvaluationRequest, policy: Policy) -> tuple[dict, str]:
    action = canonical_action(request.action_type, request.action_payload, request.resource_type, request.resource_id, policy.id, policy.version, request.scope)
    return action, action_hash(action)


def _expire_if_needed(db: Session, approval: ApprovalRequest, actor: str) -> None:
    if approval.status == "PENDING" and is_expired(approval.expires_at):
        approval.status = "EXPIRED"
        db.add(AuditEvent(actor=actor, action="approval.expired", entity_type="approval_request", entity_id=approval.id, detail={}))
        db.commit()


@router.get("/policies", response_model=list[PolicyResponse])
def list_policies(db: Session = Depends(get_db)) -> list[Policy]:
    return list(db.scalars(select(Policy).order_by(Policy.name, Policy.version)))


@router.post("/policies/evaluate", response_model=PolicyEvaluationResponse)
def evaluate(request: PolicyEvaluationRequest, db: Session = Depends(get_db)) -> PolicyEvaluationResponse:
    policy = db.get(Policy, request.policy_id)
    allowed, reason = evaluate_policy(policy, request.action_type)
    if policy is None:
        return PolicyEvaluationResponse(allowed=False, reason=reason, action_hash="", policy_id=request.policy_id, policy_version=None)
    _, computed_hash = _action_for_request(request, policy)
    return PolicyEvaluationResponse(allowed=allowed, reason=reason, action_hash=computed_hash, policy_id=policy.id, policy_version=policy.version)


@router.get("/approvals", response_model=ApprovalListResponse)
def list_approvals(status_filter: str | None = None, db: Session = Depends(get_db)) -> ApprovalListResponse:
    if status_filter and status_filter not in APPROVAL_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid approval status")
    statement = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
    if status_filter:
        statement = statement.where(ApprovalRequest.status == status_filter)
    return ApprovalListResponse(items=list(db.scalars(statement)))


@router.get("/approvals/{approval_id}", response_model=ApprovalResponse)
def get_approval(approval_id: UUID, db: Session = Depends(get_db)) -> ApprovalRequest:
    approval = db.get(ApprovalRequest, approval_id)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")
    return approval


@router.post("/approvals", response_model=ApprovalResponse, status_code=status.HTTP_201_CREATED)
def create_approval(
    request: ApprovalCreate,
    response: Response,
    idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    actor: str = Depends(require_owner),
    db: Session = Depends(get_db),
) -> ApprovalResponse:
    path = "/api/v1/approvals"
    request_hash = _idempotency_hash(request.model_dump(mode="json"))
    existing = _existing_response(db, actor, idempotency_key, "POST", path, request_hash)
    if existing:
        response.status_code = status.HTTP_201_CREATED
        return existing

    policy = db.get(Policy, request.policy_id)
    allowed, reason = evaluate_policy(policy, request.action_type)
    if not allowed or policy is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)
    _, computed_hash = _action_for_request(request, policy)
    approval = ApprovalRequest(
        policy_id=policy.id,
        policy_version=policy.version,
        action_type=request.action_type,
        action_hash=computed_hash,
        action_payload_json=request.action_payload,
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        requested_by=actor,
        reason=request.reason,
        expires_at=request.expires_at,
    )
    db.add(approval)
    db.flush()
    payload = ApprovalResponse.model_validate(approval).model_dump(mode="json")
    db.add(AuditEvent(actor=actor, action="approval.requested", entity_type="approval_request", entity_id=approval.id, detail={"action_hash": computed_hash, "action_type": approval.action_type}))
    db.add(IdempotencyRecord(actor=actor, key=idempotency_key, method="POST", path=path, request_hash=request_hash, status_code=201, response_body=payload))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_response(db, actor, idempotency_key, "POST", path, request_hash)
        if existing:
            response.status_code = status.HTTP_201_CREATED
            return existing
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unable to create approval request")
    return ApprovalResponse.model_validate(payload)


def _decide(approval_id: UUID, decision: str, body: ApprovalDecisionInput, response: Response, idempotency_key: str, actor: str, db: Session) -> ApprovalResponse:
    path = f"/api/v1/approvals/{approval_id}/{decision.lower()}"
    request_hash = _idempotency_hash({"decision": decision, **body.model_dump(mode="json")})
    existing = _existing_response(db, actor, idempotency_key, "POST", path, request_hash)
    if existing:
        return existing

    approval = db.scalar(select(ApprovalRequest).where(ApprovalRequest.id == approval_id).with_for_update())
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")
    _expire_if_needed(db, approval, actor)
    if approval.status == "EXPIRED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval request has expired")
    if approval.status != "PENDING":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval request is not pending")
    policy = db.get(Policy, approval.policy_id)
    allowed, reason = evaluate_policy(policy, approval.action_type)
    if not allowed or approval.policy_version != getattr(policy, "version", None):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    approval.status = "APPROVED" if decision == "APPROVE" else "REJECTED"
    db.add(ApprovalDecision(approval_id=approval.id, decided_by=actor, decision=decision, reason=body.reason))
    if decision == "APPROVE":
        db.add(ActionAuthorization(approval_id=approval.id, action_hash=approval.action_hash, scope="ONCE", expires_at=approval.expires_at))
    db.flush()
    payload = ApprovalResponse.model_validate(approval).model_dump(mode="json")
    db.add(AuditEvent(actor=actor, action=f"approval.{decision.lower()}d", entity_type="approval_request", entity_id=approval.id, detail={"reason": body.reason}))
    db.add(IdempotencyRecord(actor=actor, key=idempotency_key, method="POST", path=path, request_hash=request_hash, status_code=200, response_body=payload))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_response(db, actor, idempotency_key, "POST", path, request_hash)
        if existing:
            return existing
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval request was changed concurrently")
    return ApprovalResponse.model_validate(payload)


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalResponse)
def approve_approval(approval_id: UUID, body: ApprovalDecisionInput, response: Response, idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> ApprovalResponse:
    return _decide(approval_id, "APPROVE", body, response, idempotency_key, actor, db)


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalResponse)
def reject_approval(approval_id: UUID, body: ApprovalDecisionInput, response: Response, idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"), actor: str = Depends(require_owner), db: Session = Depends(get_db)) -> ApprovalResponse:
    return _decide(approval_id, "REJECT", body, response, idempotency_key, actor, db)
