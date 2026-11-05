# API specification — Sprint 2 Module 1

`GET/POST /api/v1/ai/research/{id}/workflow` reads/creates a draft workflow with a
zero-cost `VALIDATE_RESEARCH_DRAFT` task. The existing Workflow lifecycle and task
approval API enforce execution. This validates fields, not market truth or AI output.

Step 6 consent API: `GET /api/v1/ai/control`, `GET /enable-action`, and idempotent
Owner-only `POST /enable` and `/disable`. The existing Approval Center approves a
version-bound enable action. This is global consent only: each future inference must
still independently pass policy, one-time approval and budget reservation; no AI
execution path is currently available.

Owner-authenticated `GET /api/v1/ai/prompts` lists versioned prompt records.
Owner budget settlement can record a verified actual above a reservation; the
actual counts against the hard stop. Release cannot record an overage. Neither
endpoint grants permission for an AI request.

Owner-only idempotent `POST /api/v1/ai/providers/{id}/default` selects one default;
`GET/POST /api/v1/ai/providers/{id}/prices` lists/creates immutable price versions.
Mutations are validated and audited. Selecting a provider or price cannot run AI.

Step 6 adds Owner-only paginated `GET/POST /api/v1/ai/research`,
`GET /{id}` and `GET/POST /{id}/sources`. Mutations are idempotent and audited.
Only Owner-entered DRAFTs and UNVERIFIED excerpts are stored; URLs are not fetched,
and no execution endpoint exists.

`GET /api/v1/ai/agent-profiles` and idempotent Owner-only
`PUT /api/v1/ai/agent-profiles/{agent_id}` configure provider/model and resource
limits for an existing logical agent. Configuration is not authorization to run AI.

## Step 6 provider configuration — IN_PROGRESS

Owner-authenticated `GET/POST /api/v1/ai/providers`, `PATCH /api/v1/ai/providers/{id}`
and `POST /api/v1/ai/providers/{id}/archive` store configuration only. Mutations
require `Idempotency-Key`, use audit logging and never return the credential.
Provider credentials are encrypted with a deployment-supplied `AI_CREDENTIALS_KEY`;
missing or invalid keys fail closed. Enable refers to configuration only and does
not enable model execution. There is no connection-test or inference endpoint.
Saved URLs are not yet authorized or checked for safe network access.

## Step 5 workflow contract — RELEASED in v28.0.0

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
