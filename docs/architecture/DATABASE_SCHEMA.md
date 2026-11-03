# Database schema

## Step 5 schema — RELEASED in v28.0.0

`20261103_0005` adds workflows, tasks, dependency edges, execution attempts and
events with UUIDs, composite workflow-scoped foreign keys and unique attempts.
`20261103_0006` adds lease fencing, immutable action/policy/authorization snapshot
and retry scheduling fields. Both are forward-only and leave existing data intact.
The earlier Step 5 checkpoint below is historical; worker recovery is implemented.

Workflow transitions: DRAFT → PENDING_APPROVAL → APPROVED → QUEUED → RUNNING;
RUNNING can pause, complete, fail or cancel, PAUSED can resume through QUEUED or
cancel. Draft/pending/approved may cancel; pending/approved may reopen as DRAFT
with a new version. Completed, failed and cancelled workflows are terminal.
Tasks move PENDING → BLOCKED/READY → RUNNING → SUCCEEDED/FAILED/RETRY_WAIT;
retry requires a new action approval, and pending work can be cancelled. Full
transition rules and allowed edge cases are in `app/orchestration/state.py`.

## Step 5 — in progress

Forward-only `20261103_0005` adds workflow, task, dependency, execution and event
tables. Composite FKs constrain dependency/event tasks to their workflow; execution
attempts and idempotency keys are unique. Lease columns do not implement a worker
or recovery by themselves. Verified fresh PostgreSQL upgrade; execution tests remain.

## Sprint 2 Module 1 — Policy & Approval

Migration `20261031_0002_policy_approval` adds four PostgreSQL tables.

| Table | Purpose | Key protection |
| --- | --- | --- |
| `policies` | Versioned policy rules | unique `(name, version)` |
| `approval_requests` | Immutable action proposal and result state | policy FK; action-hash/status/expiry indexes |
| `approval_decisions` | Owner decision record | one decision per approval |
| `action_authorizations` | Executable, one-time approval token | one authorization per approval; status/scope checks |

Money, usage, opportunities and workflows are not part of this migration. No existing table was dropped or altered destructively.

## Sprint 2 Module 2 — Finance & Budget

Migration `20261031_0003_budget_reservations` adds `budget_accounts`, `budget_reservations`, `usage_records` and `cost_records`. All monetary fields are `NUMERIC(18,6)` in USD. An expired reservation remains committed until a settle/release operation supplies its actual cost.
# Step 4 schema addition

Forward migration `20261102_0004` extends `20261031_0003` with opportunities,
evidence, estimates, score details and evaluation history. Verified against fresh
PostgreSQL 16; no production volume reset. See [engine schema](OPPORTUNITIES.md).
