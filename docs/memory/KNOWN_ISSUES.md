# Known issues

## v31.0.0

- No test contacts Tavily, Brave, ACCESSTRADE or Facebook; clients follow the documented API
  shapes with fake transports. Watch the first real search, import and post.
- ACCESSTRADE's tracking-link host is taken from the official API response (not documented).
- Product prices imported from ACCESSTRADE are the listing values the Owner saw, not re-fetched.
- Facebook Page posts are text + link (no images yet). Revenue tracking (orders, commission) is
  Step 8.
- Local test stacks on this host need fsync off (slow disk); CI is unaffected.

## v30.0.0

- No browser E2E runs a content batch through a real AI provider (CI has none);
  drafting is covered by PostgreSQL integration tests with fake transports, and review,
  export and publish records by API and component tests.
- Content checks are rule-based (phrases, numbers, web addresses, 3-word shingles); they
  assist and never replace the Owner's reading. Media rights and ads/tax are always
  Owner-confirmed.
- The app does not track clicks, orders or commissions yet (Step 8).

## Security — open ports (found 2026-11-06, Owner: fix later)

The host has a public IP and iptables `INPUT ACCEPT`. The web (3000) and API (8000) ports
answer over plain HTTP from the internet, and sign-in has no attempt limit. The Owner chose
to defer the fix (HTTPS, OTP, rate limiting, loopback binding) until the domain is ready.

## v29.2.0

- Auto-run is covered by PostgreSQL integration and component tests with fake
  provider transports; no browser E2E drives a full auto-run.
- A research draft can have only one workflow. If its workflow FAILS (for example
  the validation step without sources), create a new research draft.
- The one-click flow approves the workflow and the plan from the Workflow page after
  a confirmation dialog; both approvals are still recorded in the Approval Center.

## v29.1.0

- Remembered sign-in sessions are stored in localStorage; use "Remember me" only on
  a personal device. Rotate `SESSION_SECRET` to revoke every session.
- The AI stage approval fix is covered by component tests and the existing
  PostgreSQL API pipeline test; no browser E2E runs a full AI stage against a real
  backend because CI has no provider.

## Step 6 v29.0.0 — current known limitations

- No test or CI run contacts a real provider; adapters are verified against
  documented response shapes with fake transports. The first real call on a new
  model should be watched and reconciled by the Owner.
- OPENAI_COMPATIBLE and custom base URLs can be stored but are denied for
  execution/connection tests (no SSRF-safe allowlist for arbitrary hosts).
- Token-based cost is an estimate; provider billing caps are not enforced by the
  provider. Unknown outcomes keep their hold until Owner settle/release.
- Source verification is an Owner attestation; the server never fetches or checks
  a URL. Model output can still be wrong even when it cites verified sources.
- Changing a source's verification after a task approval changes the action hash;
  the approval then no longer matches and must be requested again (fail closed).
- Anthropic structured output relies on prompt instructions plus strict server
  validation (a fenced JSON block is tolerated); invalid output fails the stage.
- AI_CREDENTIALS_KEY rotation is still manual; losing it makes stored keys unreadable.
- Older entries below describe earlier checkpoints and are superseded where they differ.

## Checkpoint push clarification — 2026-11-05

The latest reconciliation/idempotency edits were included in a fresh 100-test
backend PASS on isolated PostgreSQL at migration 0017. Prior notes saying they have
not been rerun are historical. This does not add dedicated AI concurrency/crash,
full AI research E2E or production provider verification; those gaps remain open.
The feature remains paused and IN_PROGRESS. The new push needs its own GitHub CI;
previous successful CI is not evidence for the new commit.

## Latest Step 6 checkpoint — paused by Owner, 2026-11-05

The new local execution path is partially integrated and tested with an injected
fake provider transport. Seed prompt 1.0.0 still explicitly denies provider
execution; API/UI execution availability remains false. Only the OpenAI wire/dispatch
path is implemented locally; Gemini, Anthropic and compatible runtime adapters,
connection tests, substantive research agents, source retrieval/verification,
Opportunity generation and usage dashboard remain incomplete. Full AI concurrency,
E2E, Docker and security acceptance have not passed. Latest finance reconciliation
and compatibility edits need retesting. Unknown charges remain reserved; token-rate
cost is not confirmed billing. No absolute provider billing cap is claimed.

CI SUCCESS applies to pushed commit 2647d60, not uncommitted invocation code.
Earlier statements that no invocation code exists are historical, not current.

Research drafts can now have a deterministic validation workflow. AI invocation,
billing-uncertainty accounting, live provider integration and substantive research
agents remain incomplete. Transport primitives are unconnected and do not by
themselves satisfy the execution-boundary or complete SSRF acceptance gates.

Owner-confirmed overage can now be recorded and included in the hard stop; the old
note that all over-reservation settlement is rejected is historical. No AI usage
reconciliation workflow exists yet: unknown provider charges must remain reserved
and are not automatically assumed zero.

Research draft/source UI and API now exist, but no live research, source fetch,
verified citation checking, agent execution, budget settlement of uncertain charges,
connection test or complete Step 6 workflow exists. Offline OpenAI serialization is
not a production adapter. Release v29.0.0 remains blocked by incomplete acceptance.

Step 6 agent profile configuration API/UI now exist; older notes below that say
model assignment is entirely absent are historical. Live execution, model capability
verification, global AI enablement and provider connection testing remain absent.

## Step 6 provider checkpoint — current

Provider configuration and encrypted storage now exist; earlier notes saying they
do not exist are superseded. Live providers, connection testing, model assignment,
research execution and usage accounting remain unavailable. The master encryption
key cannot yet be rotated automatically; loss of the key prevents decryption.
Provider base URLs are stored only, not SSRF-cleared or fetched. Budget overage and
unknown provider usage still require a safe reconciliation design before calls.

## Step 6 — current open work

Provider management, encrypted credentials, live integrations, research execution,
source retrieval, usage accounting, workflow integration and frontend are not yet
implemented. Existing budget settlement rejects actual amounts above reservations;
provider overage and unknown usage require a safe reconciliation design before any
paid call is permitted. Prompt separation alone is not a complete injection defense.
No Step 6 migration, integration/E2E/security/runtime or release gate is verified.

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

