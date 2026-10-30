# Sprint 1: control-plane specification

## Boundary

This increment implements configuration and traceability only. It does not call an AI provider, execute code, create a payment, publish content, or perform an external business action. Therefore no outside cost or customer-facing effect can originate from the current API.

## Data model

| Table | Purpose | Integrity rule |
| --- | --- | --- |
| `agents` | The seven logical workforce roles | `name` and `role` are unique. |
| `audit_events` | Append-only configuration audit trail | Event time is indexed. |
| `idempotency_records` | Stored response for a state-changing request | `(actor, key)` is unique; key reuse must match method, path and body hash. |

The initial migration uses UUID identifiers and timestamps. The later finance migration must use `NUMERIC` for all monetary values and must not retrofit mutable ledger rows into this control-plane migration.

## HTTP contract

| Route | Purpose | Control |
| --- | --- | --- |
| `GET /health/live` | Process liveness | Public |
| `GET /health/ready` | Process readiness | Public |
| `GET /api/v1/dashboard` | Basic operational counts and declared budget | Owner bearer token |
| `GET /api/v1/agents` | Registered agent roles | Owner bearer token |
| `PATCH /api/v1/agents/{id}` | Enable or disable a role | Owner bearer token, `Idempotency-Key`, audit event |
| `GET /api/v1/audit-events` | Recent audit history | Owner bearer token |

FastAPI publishes the same contract as OpenAPI at `/openapi.json` and Swagger UI at `/docs`.

## Operational configuration

`OWNER_API_KEY` is a secret, never a database value or audit field. Production startup rejects the example value. `MONTHLY_BUDGET_USD=50` is exposed as a declared limit only; the atomic reservation and reconciliation mechanisms are a Sprint 2 prerequisite for a real hard cap.

## Next migration

Add policies, approvals, budget accounts/reservations, opportunities and workflow state transitions together. External execution must remain disabled unless that migration can atomically prove an approved action and sufficient reserved budget.
