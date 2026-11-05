# Changelog

## v29.0.0 — Step 6 AI Brain & Research Agents — RELEASED

- Release: https://github.com/haiops18/makemoney/releases/tag/v29.0.0

- Seven-stage AI research pipeline (plan, market, competitors, opportunity,
  financial, risk, report) on the existing workflow, approval, budget-reservation
  and worker-lease controls; each stage needs its own exact one-time approval.
- Verified adapters for OpenAI Responses, Anthropic Messages and Gemini
  generateContent on official endpoints only; custom URLs/OPENAI_COMPATIBLE denied.
  One pinned-HTTPS dispatch per approval, no tools, retries or fallback.
- Owner source verification (VERIFIED/REJECTED); only verified sources support a
  FACT, rejected sources are never sent. Prior stage outputs passed as untrusted input.
- Durable invocation outcomes and usage; unknown outcomes keep their budget hold;
  AI usage dashboard with Owner settle/release reconciliation.
- Zero-cost provider connection test (model listing) gated by global consent.
- Promotion of a completed research report to an unscored DRAFT opportunity with
  Owner sources as evidence. Migrations 0007–0018 (forward-only).
- Earlier Step 6 foundation: encrypted provider keys, agent profiles, versioned
  Decimal prices, immutable prompts, research drafts, default-off global consent,
  verified overage settlement.

## v28.0.0 — Step 5 Workflow Orchestration — RELEASED

- Added Owner-only workflows, ordered dependencies, immutable attempt/event history,
  separate action-bound workflow and task approvals, and transactional audit.
- Added PostgreSQL-backed worker leases, concurrency-safe claims, bounded retry,
  crash recovery and cooperative cancellation for two pure validation handlers.
- Added API-backed workflow command center and isolated PostgreSQL/Compose E2E jobs.
- No external execution, paid calls, AI inference, publication or payments.
- Main, tag and release CI passed. Release: https://github.com/haiops18/makemoney/releases/tag/v28.0.0

## v27.0.0 — 2026-11-02 — RELEASED

- Opportunity database/API, manual evidence, Decimal financial scenarios, weighted
  versioned scoring, severe-risk disqualification, evaluation history and advisory comparisons.
- React overview KPIs, editable opportunities, evidence/scenario/evaluation forms,
  financial/score detail and 2–5 comparison with responsive light/dark styling.
- PostgreSQL idempotency concurrency, immutable audits, forward-only migration,
  scoped secret review, dependency audits and real API CI/E2E verification.
- Verified: 32 backend, 10 frontend, 2 Playwright tests; main/tag/release CI PASS.
- Release: https://github.com/haiops18/makemoney/releases/tag/v27.0.0

## v26.4.0 — Frontend Stabilization

- Moved React bootstrap into `main.tsx` and application shell into `src/app/App.tsx`.
- Added Admin username/password login backed by short-lived in-memory signed sessions; Owner API key remains server-only.
- Added Playwright Chromium E2E smoke coverage for authentication, navigation, language, unavailable state and mobile navigation.
- Added PostgreSQL concurrency integration verification to the required local quality gate.

## Unreleased — FE-P2 Command Center quality

- Added full Vietnamese and English UI resources, accessible loading/error/empty states, responsive command-center design tokens, search/filter controls, confirmation dialogs and success toasts.
- Added real API views for recorded finance costs/usage, richer approval details and dashboard control state without inventing unavailable business data.
- Added frontend component tests, explicit TypeScript typecheck command, Docker runtime smoke automation and a Docker CI job.
- No Opportunity, Project or Workflow API or external execution was added.

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

# Unreleased — Step 4 Opportunity Discovery

- Added opportunity schema/API, Decimal scenarios, versioned scoring/risk disqualification and advisory comparisons.
- Added existing React UI forms, scoring history and comparison, isolated PostgreSQL/Compose tests and real API Playwright verification.
- Local results: 18 backend, 7 frontend, 2 Playwright passed. Release/version pending authenticated remote verification.
- v27.0.0 candidate update: overview KPIs, enriched financial list/detail and three-scenario comparison; one-month net ROI includes setup investment; 32 backend and 9 frontend tests passed. PostgreSQL idempotency concurrency and backend dependency audit verified; final CI/release pending.
- Final local verification: 32 backend, 10 frontend, 2 expanded real-runtime Playwright tests passed. Fixed creation/list race and retained scenario form inputs during refresh.
