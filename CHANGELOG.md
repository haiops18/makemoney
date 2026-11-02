# Changelog

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
