# Release history

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
