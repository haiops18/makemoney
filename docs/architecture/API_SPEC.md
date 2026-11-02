# API specification — Sprint 2 Module 1

## Step 5 current workflow contract — IN_PROGRESS

All paths below are under `/api/v1/workflows`, require Owner authentication and
mutations require `Idempotency-Key`. Lists support pagination. `GET /` and `POST /`
list/create; `GET /summary` and `/recent-executions` provide dashboard data;
`GET/PATCH /{id}` reads/edits a draft. `GET/POST /{id}/tasks` reads/adds tasks;
`GET /{id}/events` and `/executions` expose the audit timeline and attempts.
`POST /{id}/submit`, `/start`, `/pause`, `/resume`, `/cancel`, `/reopen` enforce
the workflow state machine. `GET /{id}/tasks/{task_id}/approval-action` returns
the exact server-generated action for the existing Approval Center;
`POST /{id}/tasks/{task_id}/queue` consumes its one-time approval and enqueues it.
Submit approval and task approval are separate; neither grants future actions.
Worker claims revalidate policy, approval, dependencies and zero-cost allowance.
The older Step 5 checkpoints immediately below are historical.

Step 5 adds `POST /api/v1/workflows/{id}/submit` (creates an existing Approval
Center request tied to a canonical workflow snapshot), `POST .../{id}/start`
(consumes that approval and queues; does not execute a task), and
`GET .../{id}/tasks/{task_id}/approval-action` (returns the canonical task action
for Owner approval). Task execution/worker endpoints remain unavailable.

## Step 5 draft API — IN_PROGRESS

Owner-only `GET /api/v1/workflows`, `POST /api/v1/workflows`,
`GET /api/v1/workflows/{id}` and `GET/POST /api/v1/workflows/{id}/tasks`.
POST operations require an idempotency key and write audit events transactionally.
Only DRAFT tasks may be added, with enabled roles, allowlisted types and existing
same-workflow dependencies. No execution/approval lifecycle endpoint is available.

All endpoints below require `Authorization: Bearer <OWNER_API_KEY>`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/policies` | List enabled/disabled policies. |
| POST | `/api/v1/policies/evaluate` | Evaluate an action against an exact policy. |
| GET | `/api/v1/approvals` | List approval requests; optional `status_filter`. |
| POST | `/api/v1/approvals` | Create a pending approval. Requires `Idempotency-Key`. |
| GET | `/api/v1/approvals/{id}` | Read exact approval state. |
| POST | `/api/v1/approvals/{id}/approve` | Owner approves and creates a one-time authorization. Requires `Idempotency-Key`. |
| POST | `/api/v1/approvals/{id}/reject` | Owner rejects. Requires `Idempotency-Key`. |

The server, not the client, creates `action_hash` from canonical JSON. An expired, rejected, consumed, hash-mismatched or out-of-policy authorization is denied.

## Finance API

`GET /api/v1/budgets`, `GET /api/v1/budgets/current`, `POST /api/v1/budgets/reservations`, `POST /api/v1/budgets/reservations/{id}/settle`, `POST /api/v1/budgets/reservations/{id}/release`, `GET /api/v1/finance/usage`, and `GET /api/v1/finance/costs` require Owner authentication. Mutations require `Idempotency-Key`.
# Opportunity API addition — Step 4 candidate

See [Opportunity contracts and formulas](OPPORTUNITIES.md) for the Owner-only
`/api/v1/opportunities` routes, mutation idempotency, risk and financial semantics.
