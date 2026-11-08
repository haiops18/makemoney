# Current task

## Step 7B — 2026-11-09 — release v31.0.0

PR #14 (integrations), #15 (discovery), #16 (ACCESSTRADE, auto checks, proposals) and #17
(scheduled Facebook posting + security review fixes) merged by Claude on the Owner's instruction.
Release branch release/v31.0.0: version 31.0.0 and docs. Next: CI, merge, tag, release, redeploy
(migrations 0023–0026), then the Owner tries the flow on the server.

## Step 7A — 2026-11-08 — PR4 of 4: release v30.0.0

PR #11 and #12 merged by Claude on the Owner's explicit instruction (main 81d9633).
PR4 on branch release/v30.0.0: E2E extended to activate a campaign and create a content
batch (no AI call), security review of Step 7A, docs, version 30.0.0.
Next: CI, merge, tag v30.0.0, release, redeploy (migrations 0020–0022).

## Step 7A — 2026-11-08 — PR3 of 4: Level B review

PR2 is open as #11 and CI passed. The auto-mode classifier blocked its merge ("Merge Without Review"); the Owner must merge it.
PR3 is on branch feat/step7a-pr3-level-b-review, stacked on PR2. It adds:
- rule checks and Owner attestation;
- Owner edits as versions, approve/reject;
- export with the real link and disclosure;
- publish records and the review UI.
Migration: 20261107_0022.
Next: PR4 (E2E, docs, security review, release v30.0.0).

## Step 7A — 2026-11-07 — PR2 of 4: AI content drafts

PR1 merged as #10 (e2a2dfc). Branch feat/step7a-pr2-content-ai.
PR2 adds:
- the output-contract registry (the research wire format is unchanged);
- the content_draft prompt and contract;
- content batches as CONTENT runs with frozen snapshots;
- materializing drafts, campaign usage, and the Content tab.
Migration: 20261107_0021.
Local gates:
- backend: 119 unit tests and 146 PostgreSQL tests;
- frontend: 52 tests plus lint, typecheck and build;
- E2E: 8 passed, 1 skipped, in a CI-like run (fresh DB, pytest, then Playwright).
Note: the Step 6 E2E depends on pytest leaving fewer than 25 providers and the research-role profiles as they were. The content tests create one provider and touch only the content profile.
Next: PR3 (checks, review, approve or reject, versions, export, publish record).

## Step 7A — 2026-11-07 — AI Content & Affiliate Factory, PR1 of 4

Branch feat/step7a-content-factory. Plan approved by the Owner (docs/planning/STEP7A_ARCHITECTURE.md §10).
PR1 contains the campaign data module, migration 20261107_0020 and the Campaigns page. It has no AI and no external action.
Local gates:
- backend: 104 unit tests (SQLite) and 128 on isolated PostgreSQL;
- frontend: lint, typecheck, 48 tests, build;
- Playwright: 8 passed, 1 skipped, run in the Playwright 1.64.1 container because host Node is 18.
Next: PR2 (output-contract registry, content prompts, content batches).

## v29.2.0 — 2026-11-06 — workflow auto-run

Branch feat/workflow-auto-run. One approval runs every research workflow stage in
order. Next: PR, CI, merge, tag v29.2.0, redeploy (migration 0019).

## v29.1.0 — 2026-11-06 — sign-in and AI stage approval

Branch feat/login-ai-task-approval. Owner asked for a detailed usage guide, a working
step 7 (approve and run AI stages from the UI) and a sign-in screen with remember me,
Enter to sign in and a 12-hour session. After CI passes: merge, tag v29.1.0,
redeploy, and set SESSION_TTL_MINUTES=720 in the server `.env`.

## Step 6 COMPLETED — v29.0.0 released and deployed — 2026-11-05

Verified release https://github.com/haiops18/makemoney/releases/tag/v29.0.0 at
`a85484a`; main, tag and release CI PASS. Deployed locally at migration 0018.
See docs/releases/STEP6_VERIFICATION.md. Next: Step 7, subject to Owner scope.
Older Step 6 IN_PROGRESS entries below are historical.

## Step 6 implementation complete — 2026-11-05 — release verification in progress

Owner resumed Step 6 ("triển khai makemoney và làm tiếp bước 6 đến khi hoàn thành").
Branch feat/step6-ai-research, draft PR #6, target v29.0.0. Implemented: verified
OpenAI/Anthropic/Gemini adapters (official endpoints only), stage-specific immutable
prompts (migration 0018), prior-stage outputs as untrusted input, Owner source
verification, 7-stage pipeline creation, results API, promotion to DRAFT opportunity,
zero-cost connection test, AI usage dashboard with settle/release reconciliation.
Local evidence: backend 93 unit + full 110 on isolated PostgreSQL 0018 (incl. full
7-stage run across three fake providers, 4-worker single dispatch, crash after
DISPATCHED → USAGE_UNKNOWN with hold retained); frontend lint/typecheck/build and
29 tests. All provider traffic in tests is an injected fake; no real provider call.
Remaining: E2E, push, CI, merge, tag/release, production deploy. See
docs/releases/STEP6_VERIFICATION.md for final evidence.

## Owner-authorized push checkpoint — 2026-11-05 — IN_PROGRESS, implementation paused

Owner requested committing/pushing all current work after the pause. This permits
checkpoint publication to the existing feature branch/draft PR, not further feature
implementation, merge or release. This entry supersedes older statements about
uncommitted or untested changes below once the checkpoint commit is pushed.

Branch: feat/step6-ai-research; draft PR: https://github.com/haiops18/makemoney/pull/6 .
Checkpoint includes all local invocation, accounting, worker/API, migrations 0016/0017
and pause/recovery memory changes. Re-ran `alembic upgrade head` and full backend
pytest against the isolated PostgreSQL test database after the last reconciliation
and idempotency changes: 100 passed, two dependency/configuration deprecation warnings.
`git diff --check` passed; pattern-based secret review found no matching credential
patterns in the 18 changed/new files. These checks are not full Step 6 acceptance.
Prior frontend/E2E evidence: 22 component tests and three foundation runtime flows;
no new frontend changes. CI SUCCESS for 2647d60 does not cover this new checkpoint;
its GitHub CI must be checked separately after push. Do not claim full research,
provider connection tests, AI concurrency/runtime, or release gates complete.

Production prompt still denies inference; global consent defaults off and API/UI
execution_available remains false. No real paid provider calls, no merge/tag/release.
Feature implementation remains paused until Owner resumes it.

## Owner pause — 2026-11-05 — STEP_6_STATUS = IN_PROGRESS

Owner explicitly requested a pause and a detailed progress report. Do not resume
implementation until instructed. Preserve the uncommitted working tree on
`feat/step6-ai-research`; no reset/clean/checkout-discard. This entry supersedes
older checkpoint descriptions where they differ.

Pushed checkpoint: `2647d60326253ea555cb7789fa60acd02055018e`, draft PR #6
https://github.com/haiops18/makemoney/pull/6 . GitHub push/PR checks were verified
SUCCESS for backend, frontend, Docker, opportunity/workflow runtime and AI
configuration runtime. This CI covers the pushed checkpoint only.

Uncommitted: migrations 0016/0017, guarded one-shot OpenAI dispatch, atomic
approval/reservation preparation, invocation/outcome persistence, usage accounting,
AI task API/worker routing, recovery handling and finance reconciliation guards.
Isolated PostgreSQL upgraded to 0017 and full backend suite passed 100 tests after
worker integration. Subsequent edits to deterministic-task idempotency payload
compatibility and finance reconciliation have NOT been rerun. The last frontend
verification was 22 tests plus lint/typecheck/build; three real Compose E2E tests
covered provider configuration, deterministic research workflow and global consent,
not full AI research. No real provider request or expenditure occurred.

Production research prompt 1.0.0 explicitly has provider_execution=false, so the
new gate denies inference using that seed. Custom execution-enabled prompts exist
only in tests. Global consent remains default off; execution_available=false is
still reported by API/UI. New dispatch is verified with injected fake transport,
not real credentials. No Step 6 release/tag exists.

Resume: review uncommitted code; rerun tests after latest finance changes; test AI
PostgreSQL concurrency/crash/cancellation; add immutable execution prompt contracts,
verified provider adapters and connection tests; research/market/competitor/finance/
risk/auditor/report stages, evidence permissions, Opportunity integration, usage UI;
then full runtime/security/regression/CI/documentation and release gates.

## Step 6 active checkpoint — IN_PROGRESS — 2026-11-05

Migration head is `20261105_0015`: research workflows use an existing Workflow
with exactly one root (opportunity or research draft). A deterministic, zero-cost
VALIDATE_RESEARCH_DRAFT task uses the same approval, dependency, lease and audit
pipeline; it does not verify market sources or invoke AI. Old opportunity workflow
action payloads are preserved. PostgreSQL backend regression passed 92 tests,
including transport tests; frontend 22 tests, lint/typecheck/build passed. Three real
Compose E2E flows passed: configuration/prices, research workflow task execution,
and global consent. The pinned-HTTPS transport is not connected to API/worker and has not
made a real provider request. Test CI jobs exist but have not yet run on GitHub.

Remaining mandatory work: guarded per-action AI invocation and billing uncertainty
accounting, live provider adapters and connection test, source-access permissions,
research/market/competitor/financial/risk/auditor/report agents, Opportunity Engine
integration and usage dashboard, comprehensive security/runtime/regression/CI and
verified v29.0.0 release. No Step 6 completion or release may be claimed.

## Step 6 AI consent checkpoint — IN_PROGRESS — 2026-11-05

Migration 0014 adds a default-disabled global consent record and a distinct policy
requiring one-time Owner approval for AI consent/inference. Enable uses an exact
version-bound action hash; disable increments the version and invalidates old
approvals. Consent does not grant action approval, budget, network permission or
working inference: `execution_available` remains false. Workflow UI now chooses
policies by allowed action, rather than assuming the first policy. PostgreSQL
concurrency/regression passed 79 tests; frontend lint/typecheck/build and 21 tests
passed. End-to-end consent and workflow regression on Compose are being verified.
Live adapters, secure network gate, usage reconciliation and AI research execution
remain unimplemented; no paid call or Step 6 release has occurred.

## Step 6 budget safety checkpoint — IN_PROGRESS — 2026-11-05

Migration 0012 stores a versioned, read-only research prompt. Migration 0013
allows an Owner to settle a verified actual cost exceeding its reservation;
the budget summary counts the actual amount and enforces the existing hard stop.
Unknown usage remains reserved until explicitly reconciled; no inference exists.
The monthly-account creation race now rolls back only a savepoint, preserving
other work in the outer transaction. PostgreSQL concurrency and regression passed
76 tests; frontend 20 tests and two Step 6 E2E flows passed at prior checkpoint.
Live provider calls, execution boundary, research agents and release are pending.

## Step 6 pricing checkpoint — IN_PROGRESS — 2026-11-04

Migration 0010 adds an audited, single default provider, including PostgreSQL
concurrent-selection verification. Migration 0011 adds immutable Owner-entered,
effective-dated USD model prices with Decimal precision and audited API. Price
settings UI is implemented; its final browser test is pending. Backend regression
65 passed after migration 0011. Backend pip-audit found vulnerabilities in
cryptography 47, so the dependency was upgraded to 50; repeat audit reported no
known vulnerabilities. Paid AI execution and budget reconciliation remain absent.

## Most recent Step 6 verification — IN_PROGRESS

Two real Compose/Playwright tests passed with provider creation, Research Agent
model assignment, key revocation, research draft and unverified source entry.
The offline OpenAI contract rejects malformed, deeply nested and refused responses;
its three focused tests passed without network. Full PostgreSQL backend regression
was 62 passed before the last focused test; frontend lint/typecheck/build and 20
tests passed. The mock contract is not an execution boundary or a live provider.
Paid calls, protected budget accounting, live research, full E2E and release remain
unimplemented. No tag/release may be created until all mandatory gates pass.

## Step 6 research draft checkpoint — IN_PROGRESS — 2026-11-04

Added forward migration `20261104_0009`, Owner-authenticated research draft and
manual source APIs, and bilingual draft/source screen. Sources are UNVERIFIED and
never fetched. Two isolated browser E2E tests passed: provider/key/agent setup and
research draft/source entry. PostgreSQL migrations and 62 backend tests passed;
frontend lint/typecheck/build and 20 tests passed. An offline OpenAI Responses
request/response contract validates output and retains token usage on errors, but
does not perform network calls or authorize paid execution. No live adapter,
budget-bound AI execution, research agent, audit agent, financial AI or complete
Step 6 E2E/CI/release exists. Continue those tasks before any completion claim.

## Step 6 agent profile checkpoint — IN_PROGRESS — 2026-11-04

Added forward migration `20261104_0008`, Owner-only idempotent agent profile API
and Settings form for provider/model, output tokens, optional temperature, timeout,
per-run USD limit and configuration state. Profiles use existing agent identities;
configuration does not authorize inference. PostgreSQL upgrade 0007 → 0008 and
58 backend tests passed; frontend lint/typecheck/build and 18 tests passed. A real
isolated browser test of provider create/revoke passed before profile UI was added;
its expanded agent assignment test is pending. No paid call has been made.
Provider connection tests, live adapters, budget reconciliation, policy-authorized
AI execution, research, usage dashboard, full E2E and release remain outstanding.

## Step 6 provider checkpoint — IN_PROGRESS

Migration `20261103_0007` adds provider metadata and encrypted credentials;
Owner-only list/create/update/archive API uses idempotency and audit, with keys
encrypted using `AI_CREDENTIALS_KEY`. Settings UI allows configuration, replacement
and revocation. Enabling a provider is metadata only; paid execution is unavailable.
Fresh PostgreSQL migration and regression: 57 passed, including concurrent create.
Frontend lint/typecheck/build and 17 tests passed. No Step 6 E2E or release gates
have passed yet. Saved URLs have no network security approval: enforce SSRF, DNS and
redirect controls at a future execution boundary. Master-key rotation, agent model
assignments, live provider adapters, usage accounting, research workflow and UI are
still outstanding; no real provider request has been made. Prior checkpoint below
describes earlier state and is superseded where it differs.

## Step 6 — IN_PROGRESS — 2026-11-03

Baseline `cf805c85aad850c1e74d60fa7eb289e0ebc7b9b9`, v28.0.0 verified;
branch `feat/step6-ai-research`; target v29.0.0 was absent at preflight.
Added isolated, unconnected research-output contracts, explicit mock provider,
Decimal rate ceiling and versioned prompt envelope. Unknown source IDs and facts
without verified source references are rejected. These checks do not prove that a
source supports a claim or prevent prompt injection on their own. No production AI
provider, API, persistence, secret management, research execution, UI or paid-call
boundary is wired. Existing workflow gate still denies paid/external tasks.

Fresh source regression against isolated PostgreSQL: 51 passed before the last
prompt-only test addition; the 5 new AI contract tests passed separately in a
network-disabled container. No real provider call or expenditure was made.
Remaining: provider configuration/encryption, research persistence, policy/approval/
budget revalidation and accounting for unknown billed usage, safe source access,
workflow integration, UI, full E2E/security and release gates. Do not tag or mark
COMPLETED until all acceptance checks pass.

## Step 5 COMPLETED — v28.0.0

Verified release https://github.com/haiops18/makemoney/releases/tag/v28.0.0
at `bcd7a5cc29bc8e9e4bfc52cf38052c375dde2f22`; main, tag and release CI passed.
See `docs/releases/RELEASE_HISTORY.md` for tag SHA and test evidence. Next roadmap
step is Step 6 — AI Brain & Research Agents, subject to its authorized scope.
Older Step 5 IN_PROGRESS checkpoints below are historical.

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

