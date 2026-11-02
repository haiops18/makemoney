# Project status

## Latest Step 4 checkpoint — 2026-11-02

Advanced forms and comparison implemented. Isolated PostgreSQL migration and
rebuilt Compose suite: 18 backend tests passed; 7 frontend tests passed; 2
Playwright tests passed, including real API create/evidence/estimate/evaluate/
compare/audit. Release remains blocked by authentication, remote gates, backend
dependency audit and remaining acceptance limits documented in
`docs/releases/STEP4_VERIFICATION.md`. Earlier checkpoints below are historical.

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

## FE-P2 checkpoint — 2026-10-31

- **Feature ID:** FE-P2 Command Center quality. **Scope:** frontend enhancement only; no migration, backend contract or external execution change.
- **Implemented:** bilingual Vietnamese/English resources; shared responsive design system; loading/error/empty states; search/filter controls; explicit confirmation dialogs and toast feedback; API-backed recorded cost and usage sections; approval details with only backend-supported fields.
- **Controls preserved:** Owner token is runtime-only; mutations retain generated idempotency keys; missing Opportunity, Project and Workflow APIs remain unavailable states; no projected business data is rendered as fact.
- **Verification:** frontend lint/typecheck/build passed; Vitest component tests `4 passed`; Docker image build passed; backend `python -m pytest` in Docker `13 passed, 2 skipped`; `/health/ready` returned 200, frontend returned HTTP 200, and frontend Docker healthcheck is `healthy`.
- **Release status:** `RELEASE_BLOCKED`. Browser E2E/responsive interaction was not verified because no browser session is connected; GitHub CLI is unauthenticated so permissions, CI status, push, tag and GitHub Release cannot be verified. `npm audit --audit-level=critical` passed but reports 12 moderate dev dependency findings with no available fix.

## FE-Stabilization — v26.4.0 candidate

- Bootstrap refactor, Admin session login and Playwright Chromium E2E are implemented.
- Local gates: frontend lint/typecheck/build, Vitest, Playwright, Docker health/proxy and full PostgreSQL test suite pass.
- Security audit: zero critical/high; 12 moderate development-only ESLint/minimatch findings remain, with no non-breaking automatic remediation.

## S2-M3 checkpoint — 2026-11-02

- **Implemented in working tree:** opportunity UUID schema/migration `20261102_0004`, owner-authenticated CRUD, evidence capture, numeric financial estimates, versioned scoring with severe-risk disqualification, comparison and rankings endpoints.
- **Controls:** idempotency keys and audit events on mutations; evidence URLs are validated but never fetched; no crawler, paid AI call, external execution or financial ledger write is enabled.
- **Verification:** backend Docker pytest `13 passed, 2 skipped`; frontend lint, typecheck and production build passed.
- **Release status:** `RELEASE_BLOCKED`. The migration/release gate, browser E2E, Docker runtime verification and GitHub authentication/CI verification were not completed in this session. Frontend Opportunities remains an explicit unavailable state until its full API-backed command-center screen is completed.

### Continuation verification

- Previous 13-test Docker result was from a prebuilt image and is not evidence for the new module. Mounted source now passes 15 tests, with 2 PostgreSQL tests skipped.
- Basic Opportunities create/list/search/filter/pagination/detail UI now uses real API responses. Advanced forms, scenarios, scoring and comparison UI remain pending.
- Frontend lint/typecheck/build and 4 existing component tests passed. Feature-specific component and E2E coverage is still pending.
- GitHub CLI authentication fails with an invalid token. Release remains blocked.

