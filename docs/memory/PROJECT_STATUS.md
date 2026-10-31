# Project status

## Verified baseline — 2026-10-31

- **Sprint 1 control plane:** implemented and running.
- **Migration head before Sprint 2:** `20261030_0001`.
- **Runtime:** backend running on port 8000; PostgreSQL and Redis healthy.
- **Verified APIs:** health, dashboard, agents, agent enable/disable, audit events and settings.
- **Verified dashboard state:** seven configured/enabled agents, USD 50 configured monthly budget, external execution disabled.
- **Tests:** 5 backend tests passed before Sprint 2 work.

## Sprint 2

| Module | Task ID | Status | Acceptance state |
| --- | --- | --- | --- |
| Policy & Approval Engine | S2-M1 | Implemented | Verified: migration, API smoke, unit/regression and PostgreSQL concurrency tests passed |
| Finance & Budget Reservation | S2-M2 | Implemented | Verified: migration, API smoke, unit/regression and PostgreSQL concurrency tests passed |
| Opportunity Discovery & Scoring | S2-M3 | Not started | Not verified |
| Workflow Orchestration | S2-M4 | Not started | Not verified |
| Frontend command center | FE-P1 | Implemented (API-backed core) | Build and lint verified; browser/E2E tests not yet verified |

The root-level `PROJECT_STATUS.md` is a prior high-level snapshot and is preserved.

## S2-M1 checkpoint — 2026-10-31

- **Migration:** `20261031_0002_policy_approval` applied; database head verified as `20261031_0002`.
- **APIs:** policy list/evaluate; approval list/create/detail/approve/reject. All require the Owner bearer token; mutations require an idempotency key.
- **Controls:** canonical SHA-256 action hashing, exact policy-version binding, expiry checks, one-time authorization consumption under a PostgreSQL row lock, and audit events for request/decision/consumption.
- **Tests executed:** local `python -m pytest -q` = `9 passed, 1 skipped` (the PostgreSQL-marked test is intentionally skipped without its database URL); Docker PostgreSQL concurrency test = `1 passed`; Alembic offline SQL generation passed; live API smoke created then rejected a `DEMO` internal approval.
- **Remaining work:** S2-M2 Finance & Budget Reservation. No financial cap is enforced yet.

## S2-M2 checkpoint — 2026-10-31

- **Migration:** `20261031_0003_budget_reservations` applied; database head verified as `20261031_0003`.
- **APIs:** budget account/current summary; reservation create, settle and release; read-only usage and cost records.
- **Controls:** PostgreSQL account row locking; numeric `NUMERIC(18,6)` money; USD-only validation; idempotency; task de-duplication; explicit actual costs; expired reservations remain conservatively committed until reconciled; audit events.
- **Tests executed:** local `python -m pytest -q` = `13 passed, 2 skipped`; Docker PostgreSQL suite = `14 passed`; Alembic offline SQL generation passed; live budget summary returned a USD 50 account with USD 5 reserve and no spend.
- **Remaining work:** S2-M3 Opportunity Discovery & Scoring. No cost provider reconciliation or real charge exists.

## FE-P1 checkpoint — 2026-10-31

- **Implemented screens:** Dashboard, AI Workforce, Approval Center, Finance & Budget, Audit Logs and Settings; responsive dark/light layout plus navigation. UI copy is Vietnamese-first; complete English translation is pending.
- **Connected APIs:** dashboard, agents with idempotent enable/disable, approvals with explicit browser confirmation, budgets and audit events.
- **Unavailable by design:** Opportunities, Projects and Workflows display an explicit unavailable state because their backend APIs do not exist.
- **Tests executed:** TypeScript production build and ESLint passed. Docker Compose configuration validated.
- **Not verified:** component tests, E2E/browser responsive checks and Docker image runtime are pending; no test claims are made for them.

## Release checkpoint — RELEASE_BLOCKED

- GitHub remote and CLI authentication were verified; no existing tag or GitHub Release was found.
- CI and tag-triggered release workflows were added with minimal permissions.
- Release is blocked: required frontend component/E2E/browser and Docker runtime gates are incomplete; dependency audit reports two critical issues. No commit, push, tag or release was created.

