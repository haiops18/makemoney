from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ActionAuthorization, ApprovalRequest, AuditEvent, Policy


def is_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= datetime.now(UTC)


def evaluate_policy(policy: Policy | None, action_type: str) -> tuple[bool, str]:
    if policy is None or not policy.enabled:
        return False, "Policy is unavailable"
    rules = policy.rules_json
    allowed_action_types = rules.get("allowed_action_types") if isinstance(rules, dict) else None
    if not isinstance(allowed_action_types, list) or action_type not in allowed_action_types:
        return False, "Action type is not allowed by this policy"
    if rules.get("require_approval") is not True or rules.get("authorization_scope") != "ONCE":
        return False, "Policy rules are invalid for controlled execution"
    return True, "Approval is required before this action can be authorized"


def consume_action_authorization(db: Session, authorization_id: UUID, expected_action_hash: str, actor: str) -> bool:
    authorization = db.scalar(select(ActionAuthorization).where(ActionAuthorization.id == authorization_id).with_for_update())
    if authorization is None or authorization.action_hash != expected_action_hash:
        return False

    now = datetime.now(UTC)
    if is_expired(authorization.expires_at):
        authorization.status = "EXPIRED"
        return False
    if authorization.status != "ACTIVE" or authorization.scope != "ONCE":
        return False

    approval = db.scalar(select(ApprovalRequest).where(ApprovalRequest.id == authorization.approval_id).with_for_update())
    policy = db.get(Policy, approval.policy_id) if approval else None
    allowed, _ = evaluate_policy(policy, approval.action_type) if approval else (False, "Approval is unavailable")
    if not approval or approval.policy_version != getattr(policy, "version", None) or approval.status != "APPROVED" or is_expired(approval.expires_at) or not allowed:
        return False

    authorization.status = "CONSUMED"
    authorization.consumed_at = now
    approval.status = "CONSUMED"
    db.add(AuditEvent(actor=actor, action="authorization.consumed", entity_type="action_authorization", entity_id=authorization.id, detail={"approval_id": str(approval.id)}))
    return True
