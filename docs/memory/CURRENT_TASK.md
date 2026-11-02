# Current task

## Step 5 final local verification checkpoint — IN_PROGRESS

Baseline main `be9d371d659eb39e03a9c2914bee13bcf15cde51`, release v27.0.0;
candidate branch `feat/step5-workflow-orchestration`, target v28.0.0. Migrations
`20261103_0005` and `20261103_0006`, Owner workflow API, action-bound approvals,
PostgreSQL worker/lease recovery, bounded retries, cooperative cancellation and
real API command center are implemented. Only two zero-cost validation handlers
are allowlisted; paid/external actions fail closed.

Fresh isolated Compose stack: PostgreSQL migrations, backend regression and
concurrency 47 passed; frontend lint/typecheck/build and 14 component tests passed;
3 real-runtime Playwright tests passed including a worker restart and lease expiry.
Production npm audit reports zero findings; 12 moderate development findings
remain. GitHub PR, CI, tag and release verification are still required. Do not mark
COMPLETED until release is verified. Historical checkpoints below are superseded.

## Step 5 execution-control checkpoint — IN_PROGRESS

`submit` creates an existing Approval Center request bound to a server-generated
workflow/task/dependency snapshot. `start` locks the workflow, revalidates policy,
opportunity and action hash, consumes the one-time approval and queues the workflow.
Each task separately requires an exact task action approval; the transaction-bound
gate is implemented but is not connected to a worker or execution endpoint.
Only two pure, explicitly zero-cost validation handlers are allowed. Paid tasks
are denied rather than silently bypassing a reservation. PostgreSQL source suite:
41 passed, including concurrent workflow starts and approval single-consumption.
Task claiming, retries, cancellation, recovery, UI, E2E and release remain pending.

## Step 5 latest drafting checkpoint

Owner-authenticated workflow list/create/detail and draft task list/create APIs
are implemented with idempotency, audit, workflow row locking, role and same-
workflow dependency validation. Execution endpoints remain unavailable: no policy,
approval or budget execution gate is yet integrated. Fresh isolated PostgreSQL
upgrade through `20261103_0005` and source regression tests were run; schema-specific
concurrency, execution, frontend and release gates remain outstanding.

## Step 5 continuation checkpoint

Forward migration `20261103_0005` adds workflows, tasks, same-workflow dependencies,
execution attempts with lease fields and workflow events. Upgrade succeeded on a
fresh isolated PostgreSQL container. Initial allowlisted validation handlers are
pure and not wired to execution. The existing PostgreSQL regression now resolves
the actual Alembic head rather than assuming the Step 4 head. The API, execution
boundary, approval/budget gates, worker/recovery, UI and release remain unfinished.

## Current: S2-M4 / Step 5 — IN_PROGRESS

Baseline main `be9d371d659eb39e03a9c2914bee13bcf15cde51`; release v27.0.0
at `5f7441c7677ebecb1e232d4be79acf0657916dca`, GitHub main CI verified PASS.
Working tree was clean at start. Proposed target v28.0.0 remains unverified.
Phase 1 audit: migration head source `20261102_0004`; existing one-time policy/
approval and PostgreSQL budget reservations must be reused. Workflow API, schema,
worker and UI do not exist. Initial state/dependency primitives added, not wired
to persistence or execution. Next: migration, transaction-safe execution boundary,
policy/approval/budget integration, retry/recovery/cancellation, UI and full tests.
No execution, release, external calls or production data changes have occurred.

## Latest: S2-M3 / Step 4 RELEASED

Release v27.0.0 verified at `5f7441c7677ebecb1e232d4be79acf0657916dca`:
https://github.com/haiops18/makemoney/releases/tag/v27.0.0
Main/tag/release CI PASS; 32 backend / 10 frontend / 2 Playwright tests passed.
No feature work remains in this release checkpoint. Next roadmap module is
S2-M4 internal Workflow Orchestration; await Owner scope before implementation.
Historical recovery notes below are preserved.

**Task ID:** S2-M3

Final local gates passed: 32 backend, 10 frontend, 2 real-runtime Playwright.
Next: verify final PR #2 CI, merge under normal workflow, verify main CI, annotate
unique v27.0.0 tag, let release workflow verify/create release, then record evidence.

Latest candidate: v27.0.0 on PR #2. GitHub login/permissions restored and baseline
release verified. Advanced UI/KPIs/comparison implemented; 32 source backend and
9 frontend tests plus lint/typecheck/build passed. Await final E2E/CI, then
controlled merge/tag/release verification. Do not mark RELEASED before that.

Latest: advanced UI and real PostgreSQL/Compose E2E implemented and locally
verified (18 backend, 7 frontend, 2 Playwright passed). Awaiting supported GitHub
device authentication; remote gates and remaining acceptance limits are in
`docs/releases/STEP4_VERIFICATION.md`. Not RELEASED.

Continuation: backend core and basic real-data UI implemented; release blocked.
Next: finish advanced UI/forms and feature component/E2E coverage, then verify
isolated PostgreSQL migration/concurrency/runtime and restore GitHub authentication.

Implement Opportunity Discovery & Scoring without enabling crawlers, web research or agent execution.

S2-M1 and S2-M2 checkpoints are complete: policy/approval controls plus numeric, atomic budget reservations are verified.

Next acceptance target: opportunity CRUD, evidence, scenario estimates, versioned scoring and direct disqualification for severe risk. No crawler, online search or AI execution is in scope.

## Completed adjacent frontend task — FE-P2

FE-P2 Command Center quality is implemented and locally verified. It did not change the S2-M3 backend priority. Its release is blocked until browser E2E can be run and GitHub authentication/CI permission is available.

