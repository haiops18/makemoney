from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.finance.service import current_period


def _reservation(amount: str = "10.000000", task_id=None, **overrides):
    payload = {
        "task_id": str(task_id or uuid4()),
        "reserved_amount": amount,
        "currency": "USD",
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }
    payload.update(overrides)
    return payload


def test_budget_reservation_is_idempotent_and_settles_actual_cost(client, auth_headers):
    initial = client.get("/api/v1/budgets/current", headers=auth_headers)
    assert initial.status_code == 200
    assert Decimal(initial.json()["account"]["limit_amount"]) == Decimal("50")
    assert Decimal(initial.json()["available_amount"]) == Decimal("45")

    headers = auth_headers | {"Idempotency-Key": "budget-reserve-1"}
    payload = _reservation()
    first = client.post("/api/v1/budgets/reservations", headers=headers, json=payload)
    second = client.post("/api/v1/budgets/reservations", headers=headers, json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert first.json()["status"] == "ACTIVE"

    settled = client.post(f"/api/v1/budgets/reservations/{first.json()['id']}/settle", headers=auth_headers | {"Idempotency-Key": "budget-settle-1"}, json={"actual_amount": "3.250000", "reason": "Provider usage reconciled"})
    assert settled.status_code == 200
    assert settled.json()["status"] == "SETTLED"
    current = client.get("/api/v1/budgets/current", headers=auth_headers).json()
    assert Decimal(current["committed_amount"]) == Decimal("3.25")
    assert Decimal(current["available_amount"]) == Decimal("41.75")


def test_budget_rejects_insufficient_duplicate_and_invalid_currency(client, auth_headers):
    too_large = client.post("/api/v1/budgets/reservations", headers=auth_headers | {"Idempotency-Key": "budget-too-large"}, json=_reservation("45.000001"))
    assert too_large.status_code == 409

    task_id = uuid4()
    created = client.post("/api/v1/budgets/reservations", headers=auth_headers | {"Idempotency-Key": "budget-task-one"}, json=_reservation("5", task_id))
    duplicate = client.post("/api/v1/budgets/reservations", headers=auth_headers | {"Idempotency-Key": "budget-task-two"}, json=_reservation("5", task_id))
    invalid_currency = client.post("/api/v1/budgets/reservations", headers=auth_headers | {"Idempotency-Key": "budget-currency"}, json=_reservation("1", currency="EUR"))
    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert invalid_currency.status_code == 422


def test_budget_hard_stop_and_month_rollover(client, auth_headers):
    exhausted = client.post("/api/v1/budgets/reservations", headers=auth_headers | {"Idempotency-Key": "budget-exhaust"}, json=_reservation("45"))
    blocked = client.post("/api/v1/budgets/reservations", headers=auth_headers | {"Idempotency-Key": "budget-after-exhaust"}, json=_reservation("0.000001"))
    current = client.get("/api/v1/budgets/current", headers=auth_headers).json()
    december_start, january_start = current_period(datetime(2026, 12, 31, 12, tzinfo=UTC))
    assert exhausted.status_code == 201
    assert blocked.status_code == 409
    assert current["hard_stop"] is True
    assert december_start == datetime(2026, 11, 30, 17, tzinfo=UTC)
    assert january_start == datetime(2026, 12, 31, 17, tzinfo=UTC)


def test_budget_release_requires_explicit_actual_cost_and_is_audited(client, auth_headers):
    created = client.post("/api/v1/budgets/reservations", headers=auth_headers | {"Idempotency-Key": "budget-release-create"}, json=_reservation("7"))
    released = client.post(f"/api/v1/budgets/reservations/{created.json()['id']}/release", headers=auth_headers | {"Idempotency-Key": "budget-release"}, json={"actual_amount": "0", "reason": "No provider charge occurred"})
    assert released.status_code == 200
    assert Decimal(released.json()["actual_amount"]) == Decimal("0")
    actions = [event["action"] for event in client.get("/api/v1/audit-events", headers=auth_headers).json()]
    assert "budget_reservation.created" in actions
    assert "budget_reservation.released" in actions
