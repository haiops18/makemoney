# Release history

## v28.0.0 — Step 5 COMPLETED — 2026-11-03

- Release: https://github.com/haiops18/makemoney/releases/tag/v28.0.0
- Source: `bcd7a5cc29bc8e9e4bfc52cf38052c375dde2f22` (PR #4).
- Annotated tag: `be78055794cf71c2f78c713cd013c5a22d804978`; peeled commit is source above.
- Published 2026-11-03T14:25:18Z, neither draft nor prerelease.
- Main CI: https://github.com/haiops18/makemoney/actions/runs/41651941483 — PASS.
- Tag CI: https://github.com/haiops18/makemoney/actions/runs/41652606281 — PASS.
- Release workflow: https://github.com/haiops18/makemoney/actions/runs/41652606283 — PASS.
- Isolated verification: 47 backend tests, 14 frontend tests, 3 Playwright tests;
  PostgreSQL concurrency, worker recovery and Docker runtime passed.
- Twelve moderate development dependency findings remain; production audit clean.

## v28.0.0 candidate — Step 5 IN_PROGRESS

No v28.0.0 tag or GitHub Release is claimed. Implementation and final isolated
runtime/CI verification are in progress; release requires all mandatory gates.

## v27.0.0 — Step 4 RELEASED — 2026-11-02

- URL: https://github.com/haiops18/makemoney/releases/tag/v27.0.0
- Release source SHA: `5f7441c7677ebecb1e232d4be79acf0657916dca` (PR #2).
- Annotated tag object: `2c0e81e181bba4a6ba77f2eb505b852cb22ab275`.
- Published: `2026-11-02T06:47:04Z`; draft=false, prerelease=false.
- Main CI: https://github.com/haiops18/makemoney/actions/runs/41401325975 — PASS.
- Tag CI: https://github.com/haiops18/makemoney/actions/runs/41401763676 — PASS.
- Release workflow: https://github.com/haiops18/makemoney/actions/runs/41401763624 — PASS.
- Tests: 32 backend, 10 frontend, 2 Playwright; PostgreSQL/Docker/security gates verified.
- Known: 12 moderate frontend dev-tool findings; backend audit clean, no frontend high/critical.
- Status: Step 4 COMPLETED. Historical blocked/candidate checkpoints below retained.

## v27.0.0 candidate — Step 4

Baseline remote release v26.4.0 verified; target MAJOR v27.0.0 is unique as of
preflight. GitHub login and push/admin permission verified, PR #2 created.
32 backend and 9 frontend tests passed locally; final runtime/CI/tag/release
verification pending. No completed/released claim is made at this checkpoint.

## Step 4 — RELEASE_BLOCKED — 2026-11-02

No tag/release created. Supported GitHub device login awaits Owner authentication.
Local verification and remaining acceptance gaps: [Step 4 checkpoint](STEP4_VERIFICATION.md).

## RELEASE_BLOCKED — 2026-10-31

No tag or GitHub Release was created. The repository has no existing tag/release, but mandatory gates are incomplete: frontend component/E2E/browser tests and Docker runtime verification are not complete; `npm audit --audit-level=critical` reports two critical development dependency vulnerabilities. No commit/push/release was performed in this checkpoint.

## RELEASE_BLOCKED — FE-P2 Command Center quality — 2026-10-31

- **Version/tag/release URL/commit SHA:** not created.
- **Feature:** bilingual, responsive API-backed command center quality enhancement; no database or API contract changes.
- **Verified:** frontend lint/typecheck/build; 4 component tests; Docker build/readiness/frontend HTTP and healthy container probe; backend 13 passed with 2 intentionally skipped integration tests.
- **Known issues:** browser E2E is not verified because no browser session is connected; GitHub CLI has no authenticated account; audit has 12 moderate dev dependency findings with no automatic fix.
- **Release decision:** blocked. No push, tag or release is permitted until the unverified E2E and GitHub permission/CI gates are satisfied.

## v26.4.0 candidate — 2026-11-01

- Candidate includes frontend stabilization, Admin session login, Playwright E2E and Docker/CI verification improvements.
- Pending final Git commit, remote CI and GitHub Release verification.
