# Database schema

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
