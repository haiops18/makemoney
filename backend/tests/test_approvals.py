from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select

from app.approvals.service import consume_action_authorization
from app.db.models import ActionAuthorization, ApprovalRequest, Policy


def _policy(client, headers):
    response = client.get("/api/v1/policies", headers=headers)
    assert response.status_code == 200
    return response.json()[0]


def _approval_payload(policy_id, **overrides):
    payload = {
        "policy_id": policy_id,
        "action_type": "INTERNAL_WORKFLOW",
        "action_payload": {"operation": "validate"},
        "resource_type": "workflow",
        "resource_id": str(uuid4()),
        "scope": "ONCE",
        "reason": "Internal validation only",
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }
    payload.update(overrides)
    return payload


def test_policy_evaluation_is_server_hashed(client, auth_headers):
    policy = _policy(client, auth_headers)
    payload = _approval_payload(policy["id"])

    allowed = client.post("/api/v1/policies/evaluate", headers=auth_headers, json={key: payload[key] for key in ("policy_id", "action_type", "action_payload", "resource_type", "resource_id", "scope")})
    denied = client.post("/api/v1/policies/evaluate", headers=auth_headers, json={
        "policy_id": policy["id"],
        "action_type": "PUBLISH",
        "action_payload": {},
        "resource_type": "product",
        "resource_id": str(uuid4()),
        "scope": "ONCE",
    })

    assert allowed.status_code == 200
    assert len(allowed.json()["action_hash"]) == 64
    assert allowed.json()["allowed"] is True
    assert denied.status_code == 200
    assert denied.json()["allowed"] is False


def test_create_and_approve_approval_is_idempotent_and_audited(client, auth_headers):
    policy = _policy(client, auth_headers)
    headers = auth_headers | {"Idempotency-Key": "approval-create-001"}
    payload = _approval_payload(policy["id"])

    first = client.post("/api/v1/approvals", headers=headers, json=payload)
    second = client.post("/api/v1/approvals", headers=headers, json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert first.json()["status"] == "PENDING"

    approval_id = first.json()["id"]
    approved = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=auth_headers | {"Idempotency-Key": "approval-approve-001"}, json={"reason": "Owner reviewed exact action"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    actions = [event["action"] for event in client.get("/api/v1/audit-events", headers=auth_headers).json()]
    assert "approval.requested" in actions
    assert "approval.approved" in actions


def test_reject_and_expiry_are_blocked(client, auth_headers):
    policy = _policy(client, auth_headers)
    expired = client.post("/api/v1/approvals", headers=auth_headers | {"Idempotency-Key": "expired-approval"}, json=_approval_payload(policy["id"], expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat()))
    assert expired.status_code == 422

    created = client.post("/api/v1/approvals", headers=auth_headers | {"Idempotency-Key": "reject-approval"}, json=_approval_payload(policy["id"]))
    rejected = client.post(f"/api/v1/approvals/{created.json()['id']}/reject", headers=auth_headers | {"Idempotency-Key": "reject-decision"}, json={"reason": "Risk not accepted"})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"


def test_one_time_authorization_rejects_hash_mismatch_and_replay(client, auth_headers):
    policy = _policy(client, auth_headers)
    created = client.post("/api/v1/approvals", headers=auth_headers | {"Idempotency-Key": "consume-create"}, json=_approval_payload(policy["id"]))
    approval = client.post(f"/api/v1/approvals/{created.json()['id']}/approve", headers=auth_headers | {"Idempotency-Key": "consume-approve"}, json={"reason": "Owner approved internal action"}).json()

    from app.db.session import get_db
    session = next(client.app.dependency_overrides[get_db]())
    authorization = session.scalar(select(ActionAuthorization).where(ActionAuthorization.approval_id == UUID(created.json()["id"])))
    assert consume_action_authorization(session, authorization.id, "0" * 64, "owner") is False
    assert consume_action_authorization(session, authorization.id, approval["action_hash"], "owner") is True
    assert consume_action_authorization(session, authorization.id, approval["action_hash"], "owner") is False
    session.commit()
