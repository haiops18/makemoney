# Decisions

## 2026-11-06 — v29.2.0 workflow auto-run

- Owner decision ("bỏ qua bước phê duyệt các task, chỉ có 1 bước phê duyệt chung"):
  replace per-task approval with one workflow-level approval for research workflows.
  This supersedes "each stage needs its own exact one-time approval" for auto-run;
  per-task approval stays as the manual path.
- The single approval is an `AI_INFERENCE` approval on resource `workflow` under the
  AI policy, bound to a plan hash that excludes task statuses but includes everything
  that determines what is sent and what it may cost. Prior-stage outputs cannot be
  known in advance, so they are not in the plan; they are model outputs, validated as
  before, and do not change the cost ceiling.
- Fail closed without per-call approval: recompute the plan at queue, claim and
  dispatch; keep consent, policy, research cost limit and per-call reservation checks;
  stop (never retry) on any denial or failure; 12-hour grant lifetime.
- Grant executions store `auto_run_id` instead of `authorization_id` (which stays
  unique per execution); a check constraint forbids both.

## 2026-11-06 — v29.1.0 sign-in and AI task policy

- Owner request supersedes the earlier "token only in memory" rule: "Remember me"
  stores the signed session token in localStorage until its expiry; without it the
  token is kept in sessionStorage. Trade-off accepted: a script running in the page
  (XSS) could read a remembered token. Mitigations: no third-party scripts, the token
  is HMAC-signed and expires (12 h default), rotating `SESSION_SECRET` revokes all
  sessions, and any 401 clears the stored session.
- Task approvals choose their policy by task type: `AI_*` tasks use the enabled
  policy that allows `AI_INFERENCE`; other tasks keep the selected internal policy.
  The backend still enforces policy rules; the UI choice is only a convenience.

## 2026-11-05 — Step 6 completion decisions

- Adapters are a closed registry keyed by provider kind with fixed official hosts;
  the endpoint URL is part of the approved action hash and rechecked at dispatch.
- Each stage has its own prompt family; new prompt versions are added by migration,
  historical versions are never edited. The pipeline pins the newest
  execution-enabled version and effective price at creation time.
- Direct AI dependencies' validated outputs are passed as `prior_outputs` in the
  untrusted user message and are bound into the action hash.
- Source verification is a one-way Owner decision; rejected sources are excluded
  from provider requests and from promoted evidence.
- Promotion creates an unscored DRAFT opportunity (`data_origin=AI_RESEARCH`); AI
  findings are not converted into evidence records.
- Connection tests require global consent because they transmit the credential;
  they list models only and never send a prompt.
- `execution_available` now mirrors consent: it means "requestable", never "approved".

## 2026-11-05 — invocation and billing uncertainty

Use existing TaskExecution, action-level one-time approval, PostgreSQL reservation
and worker leases. An AIInvocation records one dispatch before network access;
DISPATCHED is never automatically sent again. No transaction remains open during
the provider request. Revalidate consent, profile, credentials version, immutable
prompt/price, action hash, dependencies, lease and budget before dispatch. Only an
explicitly verified adapter endpoint is admitted. Network requests have a total
deadline and no automatic retry/fallback.

Persist validated provider outcome and usage independently of worker completion,
so cancellation or an expired lease cannot erase billing evidence. Unknown usage
retains reservation; token-rate cost is pending reconciliation, not confirmed
billing. Observed cost above the estimate increases an open hold and may exhaust
the budget. Owner reconciliation is denied during PREPARED/DISPATCHED and updates
linked usage/cost records after a terminal or recovered outcome. These latest
reconciliation edits still require tests. Do not modify historical prompt versions
to enable execution. Owner paused implementation after this checkpoint.

Research may precede an opportunity: extend the existing workflow to accept exactly
one root, opportunity or research draft. Preserve old opportunity action payloads.
The research validation task checks fields and source presence only, never evidence
truth. HTTPS transport resolves every address, denies non-global destinations and
pins one public IP while verifying TLS against the approved hostname; no redirects
or automatic billing-sensitive retries. Transport alone does not authorize execution.

Global AI consent is default-off and versioned. Enabling consumes a one-time Owner
approval of the exact control version; disabling invalidates old enable approvals.
Consent is not a per-task approval, budget reservation, or network permission.

For verified provider overage, preserve the real actual settled charge even when it
exceeds a reservation. Count it against the existing monthly budget and hard stop;
this records a fact and grants no additional spend authority. Unknown final usage
must keep its reservation until explicit reconciliation. A monthly account insert
race uses a savepoint so it cannot discard authorization/audit in the outer transaction.

The initial OpenAI Responses wire contract is pure offline code with no transport;
it separates instructions, validates structured output and preserves usage on error.
It does not authorize a request, guarantee factual accuracy or serve as an adapter.

## Step 6 provider configuration

Store authenticated ciphertext bound to a provider UUID, using a Fernet key from
deployment secrets; do not return credentials or store them in audit/idempotency
records. Archive rather than delete providers. A configuration enable flag has no
authority to execute AI. URL syntax validation is not SSRF protection and must not
be reused as network authorization. Provider connection tests remain disabled.

## Step 6 initial safety decisions

Model output is untrusted and must pass strict schemas and server-side source-ID
checks; a source reference alone does not prove a factual claim. Prompt evidence is
kept in the user input, not elevated to system/developer instructions. Configured
prices use Decimal and effective versions; a ceiling is an estimate, not an absolute
provider billing guarantee. Paid execution remains denied until a transaction-safe
approval, reservation, unknown-usage reconciliation and execution boundary exist.

## Step 5 execution safety

PostgreSQL owns the queue and execution leases. Each workflow and each task action
uses the existing approval center independently; consumed authorizations cannot be
reused on recovery. Only two pure, zero-cost validation handlers are allowed; paid
or external actions are denied until a separately authorized design exists. Running
Python handlers cannot be force-killed safely, so cancellation discards their result
and lease fencing rejects late completions. No database volumes are reset.

- Workflow start consumes an approval for the exact submitted workflow snapshot;
  it does not grant task authorization. Each task binds a separate one-time
  approval to current inputs and policy. The current handler registry is pure,
  internal and explicitly zero-cost; any cost-bearing handler must be denied
  until its reservation control is implemented.

- Step 5 begins with explicit terminal state transitions and iterative cycle detection. No primitive alone authorizes execution; existing policy, one-time approval and budget services must be rechecked at the execution boundary.

- 2026-11-02: Candidate v27.0.0 follows verified remote v26.4.0 (MAJOR feature policy). Use a PR and successful CI before merge/tag; Owner already authorized controlled release.
- 2026-11-02: ROI uses a one-month net return including upfront investment: (monthly profit - setup cost) / setup cost * 100. Persist calculation version/period in assumptions. Zero investment keeps ROI UNKNOWN.
- 2026-11-02: PostgreSQL transaction advisory locks serialize retries by Owner/idempotency key; duplicate concurrent requests must create one mutation and audit event.

- 2026-11-02: Scoring version is constrained by the server and risk input is mandatory; callers cannot label arbitrary rules as a new version or implicitly claim LOW risk. Financial definitions are documented in `docs/architecture/OPPORTUNITIES.md`.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-10-31 | Keep the existing FastAPI modular-monolith layout. | Sprint 2 must extend, not rebuild, Sprint 1. |
| 2026-10-31 | Implement Policy & Approval before all other Sprint 2 modules. | Every later protected execution depends on it. |
| 2026-10-31 | Do not enable external execution or OpenAI/Codex in Sprint 2. | Controlled autonomy requires controls to precede execution. |
| 2026-10-31 | Use explicit unavailable frontend states until APIs exist. | Mock business data must not be presented as real. |
| 2026-10-31 | Approval identity is a server-side hash of canonical JSON including policy ID/version, action payload, resource and scope. | A decision cannot be replayed against a modified action or policy revision. |
| 2026-10-31 | An approval emits one `ONCE` authorization and consumption locks that row in PostgreSQL. | Concurrent execution attempts must allow at most one protected execution. |
| 2026-10-31 | Use `NUMERIC(18,6)` and USD-only finance records in the MVP. | Monetary calculations must not use floating point or silently mix currencies. |
| 2026-10-31 | Expired reservations remain committed until explicit settlement or release records the actual amount. | A worker crash or delayed provider bill must not be treated as zero cost. |
| 2026-10-31 | Keep Owner token only in React runtime memory. | Local storage and `VITE_*` variables would expose a long-lived credential to the browser bundle. |
| 2026-10-31 | Render unavailable states for APIs absent from Sprint 2. | The command center must not turn mock or inferred values into business facts. |
| 2026-10-31 | Add FE-P2 UI quality without introducing missing backend modules. | The command center can improve usability and observability while preserving fail-closed scope. |
| 2026-10-31 | Keep release blocked without a connected browser E2E session or authenticated GitHub CLI. | Required gates and repository permission must be verified, never assumed. |

