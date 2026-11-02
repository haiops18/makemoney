# API specification — Sprint 2 Module 1

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
