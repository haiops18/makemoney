# Known issues

Step 5 release gates below are resolved by verified v28.0.0; limitations concerning
zero-cost handlers, cooperative cancellation and moderate development findings remain.

## Current Step 5 checkpoint (supersedes historical checkpoints below)

- Workflow and task approvals, PostgreSQL worker, cancellation, bounded retries,
  lease recovery and API-backed UI are implemented; final release verification is
  still pending. Recovery and retry require fresh action-bound Owner approval.
- Only two pure validation handlers are registered; all paid or external actions
  are denied. Cancellation cannot forcibly stop a running Python handler: its
  result is discarded and leases fence late completion.
- Twelve moderate npm development-tool findings remain; production npm audit has
  no findings. Reassess on compatible upgrades; do not force breaking upgrades.
- GitHub CI and v28.0.0 release remain unverified; no completion is claimed.

Step 5 schema and two pure validation handlers now exist, but API execution and
policy/approval/budget integration remain unimplemented and fail closed. No worker,
retry/recovery, UI, Step 5 E2E or release is present. The initial isolated migration
upgrade succeeded; schema-specific constraint/concurrency tests are still needed.

## Step 5 implementation gaps

- Workflow persistence, API, execution boundary, policy/approval/budget integration,
  retry/recovery, frontend and Step 5 release gates remain unimplemented. Initial
  local source run: 30 passed, 4 PostgreSQL tests skipped; PostgreSQL Step 5
  concurrency and runtime have not been tested. No release tag was created.

## Released v27.0.0 — current issues

- GitHub auth/release, PostgreSQL migration/concurrency, advanced UI and runtime
  E2E blockers below are resolved; release and tag CI verified PASS.
- Twelve moderate frontend dev-tool findings remain with no compatible automated
  fix; no high/critical frontend findings. Backend pip-audit is clean.
- Domain enums remain English identifiers in the bilingual UI. No automated AI
  discovery, provider reconciliation or external execution is claimed.
- Existing control-plane readiness and dashboard copy improvements remain backlog
  items; this release did not deploy business execution or reset production data.

## v27.0.0 candidate review (supersedes earlier open items)

GitHub authentication restored. Fresh PostgreSQL migrations/concurrency and
advanced UI forms/KPIs/comparison are implemented and tested. Backend dependency
audit clean; frontend 12 moderate dev-tool findings remain. Domain enums retain
English codes in bilingual UI. Await final-commit E2E/CI/release verification.

## Latest checkpoint — 2026-11-02

The prior UI/database/test gaps below are historical: advanced forms exist,
fresh PostgreSQL migration/constraints/concurrency passed and real API E2E passed.
Remaining: GitHub device authentication and remote release gates, backend dependency
audit, technical English field labels, BASE-only comparison UI and broader mobile/
error-path coverage. Full Step 4 acceptance is not claimed.

- 2026-11-02: Opportunity basic API-backed UI exists, but advanced evidence/estimate/evaluation/edit/compare UI and feature E2E remain incomplete. New migration has not yet been verified on an isolated PostgreSQL instance. Current mounted-source backend suite passes 15 tests; 2 PostgreSQL tests skipped.

- The local Docker stack currently uses `.env.example`; its Owner key and PostgreSQL password must be replaced before any network exposure.
- `GET /health/ready` currently reports process readiness rather than a live database probe.
- Frontend has no browser/E2E/component test coverage yet; build and lint only are verified.
- Local Node 18 emits dependency engine warnings from the current ESLint dependency tree; build/lint still passed. Use Node 20+ for the supported frontend toolchain.
- Browser E2E/responsive interaction remains unverified in this environment because no browser session is connected. Component tests and Docker HTTP/runtime probes are verified separately.
- `npm audit --audit-level=critical` currently passes, but reports 12 moderate development dependency findings with no available automatic fix; reassess on dependency upgrades.
- The policy engine is intentionally limited to the seeded internal policy and `ONCE` scope. Additional policy authoring and scopes require a separate reviewed migration/API.
- Opportunity and workflow modules are not yet implemented; therefore no executable workflow can consume approvals or reserve budget yet.
- Budget enforcement is an internal control for recorded work only. It cannot guarantee a provider's delayed invoice or an externally created subscription never exceeds USD 50.
- GitHub CLI is not authenticated, so push permissions, remote CI state and release creation cannot be verified from this environment.

