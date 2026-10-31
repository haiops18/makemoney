# Code graph

```text
FastAPI main
  ├── existing control-plane routes
  └── approval_routes
        ├── require_owner
        ├── approval_schemas
        ├── action_hash (canonical action → SHA-256)
        ├── Policy / ApprovalRequest / ApprovalDecision models
        └── approval service
              └── consume_action_authorization
                    ├── SELECT ... FOR UPDATE
                    ├── Policy evaluation
                    ├── authorization + approval state update
                    └── AuditEvent
  └── finance_routes
        └── finance service
              ├── HCM monthly period → budget account
              ├── account row lock → reservation
              ├── explicit settle/release
              └── AuditEvent

Alembic 20261030_0001 → 20261031_0002_policy_approval → 20261031_0003_budget_reservations
Tests
  ├── test_approvals.py (API, expiry, idempotency, replay)
  └── integration/test_postgres_authorization.py (concurrent consumption)
```
