import hashlib
import json
from typing import Any
from uuid import UUID


def canonical_action(action_type: str, action_payload: dict[str, Any], resource_type: str, resource_id: UUID, policy_id: UUID, policy_version: str, scope: str) -> dict[str, Any]:
    return {
        "action_payload": action_payload,
        "action_type": action_type,
        "policy_id": str(policy_id),
        "policy_version": policy_version,
        "resource_id": str(resource_id),
        "resource_type": resource_type,
        "scope": scope,
    }


def action_hash(action: dict[str, Any]) -> str:
    canonical_json = json.dumps(action, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
