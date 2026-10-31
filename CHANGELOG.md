# Changelog

## 2026-10-31 — Sprint 2 Module 1

- Added the Policy & Approval Engine with owner-only APIs.
- Added policy/version-bound canonical action hashes and one-time, transactionally consumed authorizations.
- Added migration `20261031_0002_policy_approval`, API tests and a PostgreSQL concurrency test.
- No AI execution, external interaction, payment or publication was added.

## 2026-10-31 — Sprint 2 Module 2

- Added USD 50/month budget accounts with USD 5 reserve, numeric reservations and explicit settlement/release.
- Added usage/cost record schema and read APIs; no provider billing integration was added.

## 2026-10-31 — Frontend Phase 1

- Added the local-only React Command Center and Docker nginx service.
- Connected dashboard, workforce, approval, budget and audit APIs without storing an Owner token.
- Added explicit unavailable states for non-existent Opportunity, Project and Workflow APIs.
