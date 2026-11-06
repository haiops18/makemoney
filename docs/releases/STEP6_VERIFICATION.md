# Step 6 verification — AI Brain & Research Agents — v29.0.0

## Feature record

- **Feature ID:** STEP6 (S3-AI). Baseline: v28.0.0 `cf805c85aad850c1e74d60fa7eb289e0ebc7b9b9`.
- **Business requirement:** the Owner researches business opportunities with AI
  agents on Owner-supplied evidence, under explicit consent, per-task approval,
  budget reservation and auditable cost reconciliation, then promotes the result
  into the Opportunity Engine.
- **Acceptance criteria:**
  1. Providers OpenAI/Anthropic/Gemini usable only on official endpoints; custom
     URLs and OPENAI_COMPATIBLE never receive a credential or prompt.
  2. Each AI stage dispatches at most once per one-time approval of the exact
     server-built request; concurrent workers cannot double-dispatch.
  3. A crash after dispatch never redispatches and keeps the budget hold until
     Owner reconciliation.
  4. Only Owner-verified sources support a FACT; rejected sources are never sent.
  5. Seven-stage pipeline (plan, market, competitor, opportunity, financial,
     risk, report) with prior outputs passed as untrusted input.
  6. Usage dashboard with estimated / token-based / confirmed / held cost and
     Owner settle/release.
  7. Completed report can be promoted once into an unscored DRAFT opportunity.
  8. Zero-cost connection test gated by global consent.
- **Modules:** ai_brain (adapters, execution, accounting, network, prompts),
  orchestration worker, AI/research/provider/usage/control APIs, finance
  reconciliation (existing), React command center, migrations 0007–0018.
- **Database:** forward-only migrations `20261103_0007` … `20261105_0018`.
- **API:** see `docs/architecture/API_SPEC.md` (Step 6 section).
- **Frontend:** Settings (providers, prices, profiles, consent, connection test),
  AI research (drafts, sources, verification, stages, results, promotion),
  AI usage (dashboard and reconciliation), Workflows (stage approval and run).
- **Security:** Fernet-encrypted keys from `AI_CREDENTIALS_KEY`; pinned public
  HTTPS with DNS/address validation, no redirects/tools/retries; endpoint bound
  into the action hash; credential never logged, returned or stored in audit;
  model output schema-validated and labelled unverified; Owner-only, idempotent,
  audited mutations.
- **Target version:** v29.0.0 (new accepted feature → MAJOR).

## Local verification — 2026-11-05

- Backend unit (SQLite): 94 passed.
- Backend full suite on isolated PostgreSQL 16 at migration 0018: 111 passed,
  including `test_postgres_ai_pipeline.py` — full seven-stage run across fake
  OpenAI/Anthropic/Gemini transports, rejected-source exclusion, prior-output
  binding, results, usage, settlement and promotion; four concurrent workers →
  one dispatch; crash after DISPATCHED → `USAGE_UNKNOWN`, hold retained,
  reconciliation denied until recovery, no redispatch; consent-gated connection test.
- Backend suite inside the rebuilt `compose.step6-test.yml` backend image: 110
  passed (before the final review-fix test addition).
- Frontend: lint, typecheck, build PASS; 29 component tests PASS.
- `npm audit --audit-level=high`: PASS (7 moderate development-only findings);
  `npm audit --omit=dev`: 0 vulnerabilities.
- `git diff --check` PASS; pattern-based secret scan of the full diff: no matches.
- Independent code review: 1 HIGH (usage totals capped at 10,000 rows) and 3
  MEDIUM findings; all fixed in `b78866b` with tests.
- No automated test contacts a real provider; no paid request was made.

## Remote verification

- Branch CI for `b78866bda08d3e1e68d8ec21b95a4d409d1dcb0c`: run 42049940648 —
  backend (incl. pip-audit), frontend (incl. npm audit and E2E), docker-runtime,
  opportunity-runtime, workflow-runtime, ai-configuration-runtime: all PASS.
- Owner approved the merge; PR #6 squash-merged as `a85484a87cd4ec16354e8648c29e5706194c253f`
  (tree identical to the CI-verified `b78866b`).
- Main CI run 42057105462: PASS (ai-configuration-runtime first hit the 15-minute
  job timeout during Playwright install on a slow runner and was rerun unchanged).
- Annotated tag v29.0.0 object `3c640480658c00e1ae8958eb19c0e33b0d26132c` peels to `a85484a`.
- Tag CI run 42060339470 and release workflow 42060339387 (repeats all gates): PASS.
- Release: https://github.com/haiops18/makemoney/releases/tag/v29.0.0 —
  published 2026-11-05T16:04:04Z, draft=false, prerelease=false.

**Step 6 STATUS: COMPLETED / RELEASED.**

## Local production deployment — 2026-11-05

- Pre-deploy backup: `/root/makemoney-backups/auto_money-pre-v29-20261105-215654.dump`
  (pg_dump custom format, restore list verified).
- Deployed commit `b78866b` with `docker compose -p makemoney up --build -d --wait`;
  migrations 0004 → 0018 applied; existing data preserved.
- `ENVIRONMENT=production`; the previous OWNER_API_KEY was the `.env.example`
  placeholder and was rejected by the production check, so it was rotated. New
  admin password, session secret and AI_CREDENTIALS_KEY generated into the
  git-ignored `.env` (mode 600).
- Smoke: `/health/ready` 200, UI 200, unauthenticated API 401, admin login,
  AI usage / control / 8 prompt versions / 7 agents return 200; worker running.
