# Session history

## 2026-11-03 — Step 5 isolated verification

Built fresh `step5-ci` Compose stack without touching production volumes; PostgreSQL
upgraded through `20261103_0006`, 47 backend tests passed, and Playwright passed
3 tests against the real API/worker including forced test lease expiry, worker
restart, fresh approval and retry. Frontend lint/typecheck/build and 14 tests
passed. Production npm audit reports zero vulnerabilities; 12 moderate development
findings remain. Candidate remains IN_PROGRESS pending GitHub release gates.

## Step 5 lifecycle and authorization checkpoint

- Added transaction-bound task authorization primitive and an Owner-only
  approval-action endpoint. Hash includes workflow version, task and current
  opportunity input; changed input invalidates the approval. No handler runs yet.
- Added submit to existing Approval Center and start with one-time authorization;
  the latter queues a workflow and does not authorize any task or external action.
- PostgreSQL regression: 41 passed, including two concurrent start requests
  producing one success and one consumed authorization. No task claim or recovery
  concurrency claim is made. UI and GitHub release remain outstanding.

## Step 5 draft API checkpoint

- Added Owner-only workflow create/list/detail and task create/list, with audit,
  idempotency, draft-only modification, role validation and dependency parent checks.
- Added a composite FK preventing an event from naming a task from another workflow;
  upgraded a second fresh isolated PostgreSQL database after this schema change.
- Full mounted-source regression including existing PostgreSQL integration: 36 passed.
  This does not verify Step 5 task claiming, execution, retry or recovery.

## Step 5 schema continuation

- Added forward-only `20261103_0005`: workflow/task records, cross-workflow-safe
  dependency foreign keys, execution history/lease fields and workflow events.
- Fresh isolated PostgreSQL upgrade reached head. Added two strict, pure allowlisted
  validation handlers, not exposed to API or worker. No external execution enabled.
- An older PostgreSQL regression hard-coded the prior head; corrected it to compare
  against the Alembic script head rather than bypassing the migration check.

## Step 5 recovery and initial implementation

- Fetched GitHub; main baseline be9d371 clean; release v27.0.0 and main CI PASS verified.
- Audited existing one-time approval and budget reservation services, migration head
  source 20261102_0004, frontend unavailable state and CI workflow.
- Added isolated, fail-closed transition matrices and dependency cycle validation;
  these primitives do not expose an API or execute tasks. Step 5 is IN_PROGRESS.
- Mounted-source backend tests: 30 passed, 4 PostgreSQL tests skipped; no Step 5
  integration/runtime/E2E claim. `git diff --check` passed.

## 2026-11-02 — Step 4 v27.0.0 RELEASED

- PR #2 merged normally after all checks passed. Tested merge commit:
  `5f7441c7677ebecb1e232d4be79acf0657916dca`; source tree matches candidate.
- Main CI 41401325975 passed before unique annotated v27.0.0 tag was created/pushed.
- Tag CI 41401763676 and release workflow 41401763624 passed. Workflow created
  published release https://github.com/haiops18/makemoney/releases/tag/v27.0.0
  at 06:47:04 UTC. Tag object 2c0e81e181bba4a6ba77f2eb505b852cb22ab275 peels to tested commit.
- Step 4 marked RELEASED/COMPLETED only after URL/SHA/CI verification. Post-release
  documentation is recorded separately from immutable released source.
- Standalone test containers stopped without deletion; isolated Compose test
  remains available at loopback 18005. No production database/volumes reset.

## 2026-11-02 — Visual and migration review

- Reviewed real mobile screenshot at 375px, fixed dark-mode input/table contrast and scoped form spacing. Corrected screenshot and viewport/document width (375/375) verified; real runtime Playwright 2 passed again.
- Forward-only opportunity migration now explicitly refuses downgrade data deletion. Final source CI must pass before merge/tag.

## 2026-11-02 — v27.0.0 final local gate

- Completed KPI overview, financial list fields, saved detail metadata, confidence/validation-time comparison and all-scenario selector.
- Defined one-month net ROI including setup investment; assumptions preserve formula version.
- Expanded score boundaries/all risk categories, XSS escaping and response-mismatch tests. Backend 32 passed, frontend 10 passed; lint/typecheck/build passed.
- Final expanded real API E2E: 2 passed on rebuilt isolated Compose. Fixed an observed stale-list create race and scenario form reset; regression test added.
- PR #2 contains candidate; final remote CI/merge/tag/release pending. No early COMPLETED claim.

## 2026-11-02 — GitHub authentication restored

- Verified haiops18 login, push/admin permissions, no main protection/rulesets, latest release v26.4.0 and baseline CI success. That release includes migrations 0001–0003.
- Target candidate v27.0.0; not tagged/released. Working branch feat/step4-opportunity-engine.
- Added transaction advisory lock for idempotency and integrity/financial overflow guards; four concurrent API retries verified as one audited mutation. Backend source suite now 19 passed on isolated PostgreSQL.
- Backend dependency audit identified pytest vulnerability; upgraded to >=9.0.3,<10; repeat pip-audit clean. Frontend remains 12 moderate dev-tool findings, no high/critical.
- Local frontend lint/build/7 tests and 2 runtime Playwright tests passed again. Three-scenario comparison selector and localized descriptive labels added.

## 2026-11-02 — Five requested follow-up tasks

- Implemented edit/evidence/scenario/evaluation forms, score breakdown/history and 2–5 comparison UI.
- Added detail component tests and real-backend Playwright business flow; updated navigation unavailable test to Projects.
- Created isolated `compose.step4-test.yml` without production volumes; fresh PostgreSQL migration passed. Rebuilt Compose backend tests: 18 passed, zero skipped. Frontend: 7 tests passed plus lint/typecheck/build; Playwright: 2 passed on Compose loopback 18005.
- Added CI/tag verification for real PostgreSQL and runtime E2E. npm audit high gate passed with 12 moderate dev-only findings.
- Started supported GitHub device login; Owner authentication still pending. No remote version/permissions/CI/release claims. See docs/releases/STEP4_VERIFICATION.md for limits.

## 2026-11-02 — S2-M3 continuation

- Tested mounted working-tree source rather than the prebuilt Docker image; found and fixed SQLite-incompatible currency constraint causing 12 regression setup failures.
- Added lifecycle/auth/idempotency/disqualification and Decimal financial tests. Source suite: 15 passed, 2 PostgreSQL tests skipped.
- Scoring version is server-constrained; risk input is mandatory. Added row locking, null validation, disqualification transition guard and paginated evaluation history.
- Replaced unavailable Opportunities route with API-backed create/search/status filter/pagination/basic details. Frontend lint/typecheck/build and 4 existing tests pass; these tests do not cover the new screen.
- GitHub CLI token is invalid. RELEASE_BLOCKED; no commit, push, tag or release. Advanced opportunity forms, comparison UI, feature component/E2E tests, PostgreSQL migration/concurrency and runtime checks remain outstanding.

## 2026-10-31 — Sprint 2 recovery

- Verified repository root, Git branch and current commit.
- Read existing README and source; required memory files and `AGENTS.md` were absent.
- Verified the current Docker Compose stack, OpenAPI paths and Alembic head `20261030_0001`.
- Created initial project memory without overwriting existing root-level status documentation.
- Started S2-M1: Policy & Approval Engine.

## 2026-10-31 — S2-M1 checkpoint

- Added policy, approval request/decision and one-time authorization schema in migration `20261031_0002`.
- Added owner-only policy and approval APIs, canonical action hashes, idempotent mutations, expiry/replay protection and audit events.
- Verified migration head and endpoint behavior in Docker Compose.
- Verified one-time authorization concurrency against the running PostgreSQL service.
- No external action, AI call, payment, publication or public deployment was performed.

## 2026-10-31 — S2-M2 checkpoint

- Added numeric budget accounts, reservations, usage/cost records and migration `20261031_0003`.
- Added idempotent reserve/settle/release APIs with PostgreSQL locking, expiry preservation and audit events.
- Verified the full test suite against the running PostgreSQL container (14 passed).

## 2026-10-31 — FE-P1 checkpoint

- Added a local React/TypeScript/Vite Command Center with Tailwind styling, routing, query cache, schema validation and in-memory Owner token handling.
- Connected only existing APIs and added explicit unavailable states for modules whose APIs do not exist.
- Added a Docker nginx frontend service reverse-proxying `/api` and `/health` to backend.
- TypeScript production build and ESLint passed; browser/E2E/component tests remain unverified.

## 2026-10-31 — Release automation checkpoint

- Verified GitHub authentication and configured CI plus tag-triggered release automation.
- Marked release blocked because required test/runtime gates are incomplete and dependency audit contains critical findings.

## 2026-10-31 — FE-P2 Command Center quality checkpoint

- Recovered source/memory, inspected runtime OpenAPI and verified Opportunity, Project and Workflow APIs are absent.
- Added bilingual UI resources, shared responsive states, search/filter, owner confirmation dialogs, toast feedback, finance cost/usage views, component tests and Docker smoke CI.
- Verified lint/typecheck/build, 4 component tests, Docker image build, backend `13 passed, 2 skipped`, readiness and frontend HTTP response.
- Browser E2E was not runnable because no browser session is available. GitHub CLI is unauthenticated. Recorded `RELEASE_BLOCKED`; no commit, push, tag or release was created.
- Diagnosed an Nginx container healthcheck failure: `localhost` resolved to unavailable IPv6 while Nginx listened on IPv4. Changed the probe to `127.0.0.1` and verified the frontend container is healthy.

