# Changelog

## Unreleased — Step 7B Autopilot (target v31.0.0)

- PR-A, integrations profile (no automatic action):
  - New **Kết nối** (Integrations) page: the Owner enters once a web search source
    (Tavily or Brave Search), ACCESSTRADE and a Facebook Page (numeric Page ID and Page
    access token). Tokens are encrypted on the server, write-only and never returned or
    logged; removing an integration deletes its token.
  - "Check connection" sends one request to the official host only (api.tavily.com,
    api.search.brave.com, api.accesstrade.vn, graph.facebook.com v26.0). Search checks
    use one paid query and ask first; ACCESSTRADE and Facebook checks are free reads.
  - API: `/api/v1/integrations` (create, update, archive, test). Idempotent and audited.
    Migration `20261108_0023`. The pinned HTTPS transport now builds query strings itself.

## v30.0.0 — 2026-11-08 — Step 7A AI Content & Affiliate Factory (Level B)

- PR1, campaign data with no AI and no external action:
  - Campaigns are built from an evaluated opportunity and carry an optional, Owner-entered
    affiliate disclosure (there is no default). Status moves DRAFT → ACTIVE ⇄ PAUSED →
    ARCHIVED; archived campaigns are read-only. Updates use optimistic versions.
  - Each campaign has its own sources, which the Owner verifies once. Affiliate programs
    list their allowed link hosts and tracking keys. Program terms (commission, cap,
    cookie, payout, cancellation, tax and so on) are append-only and report their
    evidence status. A product price requires a source.
  - Affiliate links must be https on an allowed host. The original URL is kept and only
    allowed tracking keys are appended. Only one active link may exist per final URL.
    The server never opens a link.
  - API: `/api/v1/campaigns` (sources, programs, terms, products, links). Every change is
    idempotent and audited. Migration `20261107_0020`.
  - UI: a new **Campaigns** page with Overview, Sources, Programs & terms, Products and
    Affiliate links tabs.
- PR2, AI content drafts (Level B, nothing is published):
  - A **content batch** freezes the campaign's non-rejected sources, the latest program
    terms (with evidence status), the product and the chosen link into a CONTENT run.
    Its workflow is validation followed by `AI_CONTENT_DRAFT` (the `content` agent).
    Batch limits must fit within the campaign AI cost limit. Creating a batch runs nothing.
  - It runs on the existing one-approval auto-run (or per-task approval), with consent,
    policy, cost-limit and budget-reservation checks on every call.
  - The model never sees the affiliate URL. It writes `{{AFFILIATE_LINK}}`, and output that
    contains any web address, an unknown source, an unverified FACT, the wrong item count
    or type, or an over-long body is rejected.
  - An output-contract registry selects the schema and validator per prompt family.
    Research requests and action payloads are byte-identical to v29.
  - Valid output becomes DRAFT content items with an immutable AI version 1, in the same
    transaction as the usage record. A unique (invocation, index) key prevents duplicates.
  - Campaign usage by batch and by agent. Content batches are hidden from the research page.
  - API: `GET|POST /campaigns/{id}/content-batches`, `GET /campaigns/{id}/content[/{cid}]`,
    `GET /campaigns/{id}/usage`. Migration `20261107_0021` adds the content tables and
    the `content_draft` prompt.
  - UI: a **Content** tab with the batch form, the one-approval panel per batch, the
    drafts with their claim labels, and the cost.
- PR3, Level B review (the app never posts):
  - Lifecycle: DRAFT → checks → CHECK_FAILED | IN_REVIEW → APPROVED | REJECTED →
    READY_TO_PUBLISH (export) → PUBLISHED (the Owner's publish record). An Owner edit
    creates a new immutable OWNER version based on the current one, keeps the AI claims
    for reference and returns the item to DRAFT. PUBLISHED items cannot be edited.
  - Rule checks run once per version: link placeholder, disclosure, claim evidence,
    price/percentage against verified data, restricted phrases (guarantees, unprovable
    superlatives, health and finance promises), other web addresses, and near-duplicates
    (3-word shingles, 80%). Media rights and advertising/e-commerce/tax are always
    NEEDS_OWNER. A FAIL can only be fixed by editing. NEEDS_OWNER becomes PASS only when
    the Owner confirms it with a note. Approval requires every check to PASS and a note.
    The system never marks content compliant on its own.
  - Export returns the text with the stored final link and the campaign disclosure (when
    one is set and missing from the text), as plain text or Markdown. A retired link
    blocks export.
  - Publish records hold the channel, an https post URL and a time that is not in the future.
    Each URL is recorded only once.
  - API: `POST /campaigns/{id}/content/{cid}/versions|checks/run|checks/{name}/attest|approve|reject|export|publish-records`.
    Migration `20261107_0022`. All changes are idempotent and audited.
  - UI: a review panel per draft (body, claims, version history, checks with Owner
    confirmation, edit, approve/reject with a note, export and copy, publish record).
- PR4, release: E2E now activates a campaign and creates a content batch through the UI
  (no AI call), security review of the Step 7A code, documentation and version 30.0.0.
  Upgrade: pull, rebuild and restart; migrations 0020–0022 run on backend start.
- Security review fixes before release:
  - The "no web address" rule for AI output and the EXTRA_LINKS check now catch any
    scheme, protocol-relative and IP addresses, punycode, short-link domains (goo.gl,
    youtu.be, amzn.to…) and any lowercase dotted name. Uppercase abbreviations (TP.HCM)
    and numbers (3.68%, 199.000đ) still pass.
  - Link and URL validation rejects backslashes, `%`/`@` in the host part and non-ASCII
    host names, so a link cannot pass the host allowlist and open another site.
  - A content batch is refused when campaign text, terms or source excerpts contain a web
    address or the real link, so the model can never receive it.
  - The campaign AI cost limit cannot be lowered below what batches already hold.

## v29.2.0 — One-approval workflow auto-run

- Added workflow auto-run for research workflows: one Owner approval ("Approve & run
  automatically") and the worker queues every stage in dependency order, with no
  per-task approval. Per-task approval remains available.
- The approval binds a server-derived plan hash: tasks and dependencies, pinned
  prompts and prices, agent profiles, provider and credential version, sources,
  both policies, consent version and the research cost limit. Every queue, claim
  and dispatch recomputes the plan; any change stops the auto-run.
- Each AI call still needs global consent, the AI policy, the research cost limit
  and its own budget reservation. The auto-run stops on failure, plan change,
  budget denial, cancellation, Owner stop or 12-hour expiry; it never retries a
  paid call. Pause halts queuing and resume continues.
- The auto-run needs at least one research source (otherwise the validation step
  would fail the workflow).
- API: `GET /workflows/{id}/auto-run-action`, `GET|POST /workflows/{id}/auto-run`,
  `POST /workflows/{id}/auto-run/stop`. Migration `20261106_0019` adds
  `workflow_auto_runs` and `task_executions.auto_run_id`.

## v29.1.0 — Owner sign-in screen and AI stage approval fix

- Fixed: requesting approval for an AI research stage on the Workflow page used the
  internal workflow policy, so the backend refused every AI stage. AI tasks now use
  the enabled `AI_INFERENCE` policy (shown on the task); internal tasks are unchanged.
  The UI blocks AI stage approval when no AI policy is enabled.
- Added a full-screen Owner sign-in page: Enter submits, empty-field validation,
  server/timeout errors, and a "Remember me" option.
- Sessions: "Remember me" keeps the session in localStorage until it expires or the
  Owner signs out and prefills the username; otherwise the session lives in
  sessionStorage for the current tab. Expired sessions are discarded and any 401
  returns to the sign-in page.
- Default session lifetime is 12 hours (`SESSION_TTL_MINUTES=720`).
- Added the Vietnamese Owner guide `docs/USER_GUIDE.md`.

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
